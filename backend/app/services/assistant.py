"""
Assistant — agentic orchestrator for L.E.A.D.S. (MasterBuildPlan §3 capstone).

A single conversational entry point: given a natural-language message, an LLM
ROUTER picks the right L.E.A.D.S. capability + extracts its arguments, the
backend executes that tool, and the assistant returns a unified reply + the
structured result + which tool it used. This ties the whole app together.

Tools it can route to: research (cited Q&A), case_brief (IRAC), explain (plain
English), compliance (permissible-purpose), citator (validate a cite), similar
(related authorities), flashcards, outline, classify (doc type), or a direct
general-information answer.

GRACEFUL: with no LLM key the router falls back to a keyword heuristic and,
failing that, to research(). Every tool call is wrapped — a tool error degrades
to a plain message, never a crash. GUARDRAILS inherited: public legal data only,
no PII, "general legal information, not legal advice."
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from . import (
    casebrief,
    citator,
    classifier,
    compliance,
    llm_router,
    plainlang,
    rag,
    study,
)

_DISCLAIMER = "General legal information, not legal advice."

# Tool catalog shown to the router LLM.
_TOOLS = [
    ("research", "Answer a legal question with citations to statutes + case law."),
    ("case_brief", "Brief a court case (facts/issue/rule/analysis/holding). Needs a citation or pasted opinion."),
    ("explain", "Rewrite legal jargon / a case / a statute into plain English."),
    ("compliance", "Analyze whether an investigative method is lawful (FCRA/FDCPA/DPPA/GLBA) + alternatives."),
    ("citator", "Validate a citation and report how often it's been cited + treatment."),
    ("similar", "Find related authorities (cases similar to a holding/issue)."),
    ("flashcards", "Make study flashcards for a topic or pasted text."),
    ("outline", "Make a study outline for a legal topic."),
    ("classify", "Identify a document's type (statute/opinion/regulation/bill)."),
    ("answer", "A direct general legal-information answer when no specialized tool fits."),
]

_ROUTER_SYS = (
    "You route a user's message to ONE L.E.A.D.S. tool and extract its arguments. "
    "Available tools:\n"
    + "\n".join(f"- {name}: {desc}" for name, desc in _TOOLS)
    + "\n\nRespond with STRICT JSON only (no markdown): "
    '{"tool": "<name>", "args": {...}, "why": "<one short reason>"}. '
    "Arg keys by tool: research={question, deep(bool)}; case_brief={citation OR text}; "
    "explain={text OR citation}; compliance={scenario}; citator={citation}; "
    "similar={text}; flashcards={topic OR text}; outline={topic}; classify={text}; "
    "answer={}. Choose 'research' for general legal questions; 'compliance' when the "
    "user asks whether something is lawful/permissible; 'case_brief'/'citator' when a "
    "case citation is central. Default to 'research' if unsure."
)

_CITE_RE = re.compile(r"\b\d+\s+[A-Z][\w.]*\.?\s*(?:\d?d|App|Supp|U\.?\s?S)?\.?\s+\d+\b|\b\d+\s+U\.?\s?S\.?\s+\d+\b")


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    if not fenced:
        m = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = m.group(0) if m else candidate
    try:
        d = json.loads(candidate)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _keyword_route(message: str) -> Dict[str, Any]:
    """No-LLM fallback router using simple signals."""
    m = message.lower()
    has_cite = bool(_CITE_RE.search(message)) or " v. " in message or " v " in f" {m} "
    if any(w in m for w in ("permissible", "is it lawful", "is it legal", "am i allowed", "can i legally", "permissible purpose")):
        return {"tool": "compliance", "args": {"scenario": message}, "why": "lawfulness question"}
    if any(w in m for w in ("plain english", "explain like", "in layman", "what does this mean", "simplify")):
        return {"tool": "explain", "args": {"text": message}, "why": "plain-language request"}
    if "flashcard" in m:
        return {"tool": "flashcards", "args": {"topic": message}, "why": "flashcards request"}
    if "outline" in m:
        return {"tool": "outline", "args": {"topic": message}, "why": "outline request"}
    if any(w in m for w in ("brief this", "case brief", "irac")) and has_cite:
        return {"tool": "case_brief", "args": {"citation": message}, "why": "case-brief request"}
    if any(w in m for w in ("still good law", "shepardize", "how often cited", "validate this cite")) and has_cite:
        return {"tool": "citator", "args": {"citation": message}, "why": "citator request"}
    return {"tool": "research", "args": {"question": message}, "why": "general legal question"}


def _run_tool(tool: str, args: Dict[str, Any], message: str) -> Dict[str, Any]:
    """Execute the chosen tool; return {reply, data, sources?}. Never raises."""
    a = args or {}
    try:
        if tool == "research":
            # Default to fast local-corpus retrieval; the router can opt into a
            # live case-law fetch with deep=true. Keeps the chat snappy.
            r = rag.answer(a.get("question") or message, deep=bool(a.get("deep", False)))
            return {
                "reply": r.get("answer", ""),
                "sources": [{"citation": c.get("citation"), "title": c.get("source_title")} for c in r.get("citations", [])],
                "data": {"conflicts": r.get("conflicts", []), "followups": r.get("followups", [])},
            }
        if tool == "case_brief":
            r = casebrief.brief(citation=a.get("citation"), text=a.get("text"))
            if "error" in r:
                return {"reply": r["error"], "data": r}
            reply = r.get("synopsis") or (f"{r.get('case_name','')}: {r.get('holding','')}").strip(": ")
            return {"reply": reply, "data": r}
        if tool == "explain":
            r = plainlang.explain(text=a.get("text"), citation=a.get("citation"))
            if "error" in r:
                return {"reply": r["error"], "data": r}
            return {"reply": r.get("plain_transcription") or r.get("overview", ""), "data": r}
        if tool == "compliance":
            r = compliance.analyze(a.get("scenario") or message)
            pp = r.get("permissible_purpose", {})
            reply = f"Verdict: {pp.get('verdict','')}. {pp.get('explanation','')}".strip()
            return {"reply": reply, "data": r}
        if tool == "citator":
            r = citator.treatment_for_citation(a.get("citation") or message)
            return {"reply": r.get("treatment", "Citator unavailable."), "data": r}
        if tool == "similar":
            r = study.similar(a.get("text") or message)
            n = len(r.get("results", []))
            return {"reply": f"Found {n} related authorit{'y' if n == 1 else 'ies'} in the corpus.", "data": r}
        if tool == "flashcards":
            r = study.flashcards(topic=a.get("topic") or "", text=a.get("text") or "")
            if "error" in r:
                return {"reply": r["error"], "data": r}
            return {"reply": f"Made {len(r.get('cards', []))} flashcards.", "data": r}
        if tool == "outline":
            r = study.outline(a.get("topic") or message)
            if "error" in r:
                return {"reply": r["error"], "data": r}
            return {"reply": f"Outline for “{r.get('topic','')}” with {len(r.get('sections', []))} sections.", "data": r}
        if tool == "classify":
            r = classifier.predict(a.get("text") or message)
            if "error" in r:
                return {"reply": r["error"], "data": r}
            return {"reply": f"Document type: {r.get('label')} ({round(r.get('confidence', 0) * 100)}% confidence).", "data": r}
    except Exception as exc:
        return {"reply": f"That tool hit an error ({exc}). Try rephrasing.", "data": {}}

    # 'answer' or unknown -> direct general-information answer (grounded if possible).
    r = rag.answer(message, deep=False)
    return {"reply": r.get("answer", ""), "sources": [{"citation": c.get("citation"), "title": c.get("source_title")} for c in r.get("citations", [])], "data": {}}


def chat(message: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Route a natural-language message to the right tool, run it, and return
    {reply, tool_used, why, sources, data, provider, disclaimer}.
    """
    message = (message or "").strip()
    if not message:
        return {"error": "Say something to the assistant."}
    history = (history or [])[-8:]  # bound the history a client can send

    # 1. Route (LLM, else keyword heuristic).
    ctx = ""
    if history:
        ctx = "Recent conversation:\n" + "\n".join(
            f"{h.get('role', 'user')}: {h.get('content', '')[:300]}" for h in history[-4:]
        ) + "\n\n"
    raw, provider = llm_router.synthesize(_ROUTER_SYS, f"{ctx}User message: {message}\n\nRoute as STRICT JSON.")
    route = _extract_json(raw) if raw else None
    if not route or not isinstance(route.get("tool"), str):
        route = _keyword_route(message)
        provider = provider or "keyword-router"

    tool = route.get("tool", "research").strip().lower()
    valid = {name for name, _ in _TOOLS}
    if tool not in valid:
        tool = "research"
    args = route.get("args") if isinstance(route.get("args"), dict) else {}

    # 2. Execute.
    out = _run_tool(tool, args, message)

    return {
        "reply": out.get("reply", ""),
        "tool_used": tool,
        "why": str(route.get("why", "")).strip(),
        "sources": out.get("sources", []),
        "data": out.get("data", {}),
        "provider": provider,
        "disclaimer": _DISCLAIMER,
    }
