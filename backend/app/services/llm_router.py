"""
LLM Router — free-first multi-provider cascade for L.E.A.D.S.

Cascade order: Groq -> Cerebras -> Gemini -> Claude (Anthropic). Keys are read
from the environment (GROQ_API_KEY / CEREBRAS_API_KEY / GEMINI_API_KEY /
ANTHROPIC_API_KEY). Cerebras (OpenAI-compatible, fast, free tier) sits second so
that when Groq's daily token cap is hit there is another quick free provider
before Gemini's throttling / the paid Anthropic tier.

GUARDRAIL: This router is a thin pass-through. It sends only the prompt the
caller built (a citation-grounded question over retrieved public/licensed legal
passages, or user-uploaded case-file text). No provider is asked to train on,
retain, or learn from any data — these are stateless completion calls.

OBSERVABILITY: every provider call + the cascade entrypoint are wrapped with
LangSmith's @traceable. Tracing is OFF unless LANGSMITH_API_KEY is set (then it
auto-enables); if the `langsmith` package is absent the decorator degrades to a
no-op. No prompt content is logged locally — traces go only to the user's own
LangSmith project when they opt in with a key.

CRITICAL DESIGN POINT: if NO provider key is configured, or every configured
provider fails, `synthesize()` returns (None, "extractive (no LLM key)"). The
caller (rag.answer / casefile.answer) then degrades gracefully to an EXTRACTIVE
answer built from the top retrieved passages + their citations. The app stays
fully functional with zero API keys.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

import httpx

logger = logging.getLogger("leads.llm_router")

# Sensible free-tier defaults; overridable via env.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
# Anthropic default is a low-cost Haiku model (aligns with .env.example). The
# Anthropic tier is last in the cascade and only reached if the free providers
# fail, so the default favors COST. Override with ANTHROPIC_MODEL for a stronger
# model. (claude-3-5-haiku-latest tracks the current Haiku release.)
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


# --- Observability (LangSmith) ----------------------------------------------
# Auto-enable tracing when the user has supplied a key but not the toggle.
if os.getenv("LANGSMITH_API_KEY") and not os.getenv("LANGSMITH_TRACING"):
    os.environ["LANGSMITH_TRACING"] = "true"
os.environ.setdefault("LANGSMITH_PROJECT", os.getenv("LANGSMITH_PROJECT", "leads"))

try:  # langsmith is OPTIONAL — degrade to a no-op decorator if unavailable.
    from langsmith import traceable as _traceable  # type: ignore

    _LANGSMITH_IMPORTED = True
except Exception:  # pragma: no cover - import guard
    _LANGSMITH_IMPORTED = False

    def _traceable(*d_args, **d_kwargs):  # no-op decorator matching @traceable(...)
        def _wrap(fn):
            return fn

        # Support both @_traceable and @_traceable(...) usage.
        if len(d_args) == 1 and callable(d_args[0]) and not d_kwargs:
            return d_args[0]
        return _wrap


def observability() -> dict:
    """Tracing status for /api/health (no secrets)."""
    enabled = bool(os.getenv("LANGSMITH_API_KEY")) and _LANGSMITH_IMPORTED
    return {
        "provider": "langsmith",
        "sdk_installed": _LANGSMITH_IMPORTED,
        "tracing": enabled,
        "project": os.getenv("LANGSMITH_PROJECT", "leads") if enabled else None,
    }


def available_providers() -> list[str]:
    """Return the list of providers that have a key configured (cascade order)."""
    out = []
    if os.getenv("GROQ_API_KEY"):
        out.append("groq")
    if os.getenv("CEREBRAS_API_KEY"):
        out.append("cerebras")
    if os.getenv("GEMINI_API_KEY"):
        out.append("gemini")
    if os.getenv("ANTHROPIC_API_KEY"):
        out.append("anthropic")
    return out


def _openai_chat(url: str, key: str, model: str, system: str, user: str) -> str:
    """Shared OpenAI-compatible chat completion (Groq + Cerebras)."""
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


@_traceable(run_type="llm", name="groq")
def _call_groq(system: str, user: str) -> str:
    return _openai_chat(
        "https://api.groq.com/openai/v1/chat/completions",
        os.environ["GROQ_API_KEY"], GROQ_MODEL, system, user,
    )


@_traceable(run_type="llm", name="cerebras")
def _call_cerebras(system: str, user: str) -> str:
    return _openai_chat(
        "https://api.cerebras.ai/v1/chat/completions",
        os.environ["CEREBRAS_API_KEY"], CEREBRAS_MODEL, system, user,
    )


@_traceable(run_type="llm", name="gemini")
def _call_gemini(system: str, user: str) -> str:
    key = os.environ["GEMINI_API_KEY"]
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={key}"
    )
    resp = httpx.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.1},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


@_traceable(run_type="llm", name="anthropic")
def _call_anthropic(system: str, user: str) -> str:
    """Anthropic Messages API via raw HTTP (no SDK dependency in Phase 0)."""
    key = os.environ["ANTHROPIC_API_KEY"]
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1500,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    blocks = resp.json().get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return text.strip()


_PROVIDERS = {
    "groq": _call_groq,
    "cerebras": _call_cerebras,
    "gemini": _call_gemini,
    "anthropic": _call_anthropic,
}


@_traceable(run_type="chain", name="llm_router.synthesize")
def synthesize(system: str, user: str) -> Tuple[Optional[str], str]:
    """
    Run the free-first cascade. Returns (answer_text, provider_label).

    On success: (text, "groq" | "gemini" | "anthropic").
    On total failure or no keys: (None, "extractive (no LLM key)") so the
    caller can fall back to an extractive, still-cited answer.
    """
    for name in available_providers():
        try:
            text = _PROVIDERS[name](system, user)
            if text:
                return text, name
        except Exception as exc:  # noqa: BLE001 — cascade must never crash a request
            # Observability: log WHY a provider was skipped (error / throttle /
            # 429) before falling through to the next provider, instead of
            # silently swallowing it. For an HTTP error, surface the status code.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status else type(exc).__name__
            logger.warning(
                "LLM provider '%s' (%s) failed: %s — falling through to next provider.",
                name,
                _model_for(name),
                detail,
            )
            continue
    return None, "extractive (no LLM key)"


def _model_for(name: str) -> str:
    return {
        "groq": GROQ_MODEL,
        "cerebras": CEREBRAS_MODEL,
        "gemini": GEMINI_MODEL,
        "anthropic": ANTHROPIC_MODEL,
    }.get(name, "?")
