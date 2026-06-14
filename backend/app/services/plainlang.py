"""
Layman's-Terms Transcriber (MasterBuildPlan §3 enhancement) for L.E.A.D.S.

Takes legal material — pasted jargon, an opinion, a statute, or a citation/
corpus source_id — and TRANSCRIBES it into plain English a non-lawyer (e.g. a
juror) can follow: a plain-language rewrite, a glossary that demystifies each
legal term, a step-by-step walkthrough, why it matters, an everyday analogy,
and a one-line bottom line. Serves the education mission (jurors, students,
self-represented people).

GUARDRAILS: explains ONLY what the source says; neutral and accurate; "general
legal information, not legal advice." Stateless LLM calls; graceful extractive
fallback (a built-in glossary of common legal terms) when no LLM key is set.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from . import llm_router
from .casebrief import _extract_json, resolve_source_text

_DISCLAIMER = (
    "Plain-language explanation for general understanding — NOT legal advice, and "
    "not a substitute for the court's actual instructions or a lawyer. AI-generated "
    "from the source text; verify against the original."
)

# Built-in glossary used by the no-LLM fallback so the transcriber is still
# useful with zero keys. Plain, juror-friendly definitions.
_GLOSSARY: Dict[str, str] = {
    "plaintiff": "the person or group who started the lawsuit (who is suing).",
    "defendant": "the person or group being sued or accused.",
    "appellant": "the side that lost below and is asking a higher court to review the decision.",
    "appellee": "the side defending the lower court's decision on appeal.",
    "petitioner": "the party who asks a higher court to hear the case.",
    "respondent": "the party responding to the petitioner's request.",
    "certiorari": "a higher court's agreement to review a lower court's decision (often 'cert').",
    "remand": "sending the case back to the lower court for further action.",
    "affirmed": "the higher court agreed with the lower court's decision.",
    "reversed": "the higher court overturned the lower court's decision.",
    "vacated": "the decision was wiped out / set aside.",
    "tort": "a wrongful act (other than a broken contract) that causes harm and can be sued over.",
    "negligence": "failing to take reasonable care, causing harm to someone.",
    "liability": "legal responsibility for something (often having to pay).",
    "statute": "a written law passed by a legislature.",
    "ordinance": "a local law passed by a city or county.",
    "injunction": "a court order telling someone to do, or stop doing, something.",
    "damages": "money awarded to make up for a harm or loss.",
    "summary judgment": "a ruling deciding the case (or part of it) without a full trial because the key facts aren't disputed.",
    "motion to dismiss": "a request to throw out a case early, before trial.",
    "complaint": "the document that starts a lawsuit and lists the claims.",
    "jurisdiction": "a court's power to hear and decide a particular case.",
    "standing": "the right to bring a lawsuit because you were actually affected.",
    "due process": "the constitutional guarantee of fair legal procedures.",
    "holding": "the court's actual decision on the legal question.",
    "dicta": "comments in an opinion that aren't part of the binding decision.",
    "precedent": "an earlier decision that guides how similar later cases are decided.",
    "stare decisis": "the principle that courts follow precedent.",
    "de novo": "reviewing something fresh, without deferring to the earlier decision.",
    "prima facie": "on its face / at first look — enough to prove a point unless disproved.",
    "pro se": "representing yourself in court without a lawyer.",
    "subpoena": "a legal order to appear or produce documents.",
    "deposition": "sworn out-of-court testimony taken before trial.",
    "discovery": "the pretrial process of exchanging evidence between sides.",
    "burden of proof": "the duty to prove a disputed claim.",
    "fdcpa": "the Fair Debt Collection Practices Act — limits how debt collectors can behave.",
    "fcra": "the Fair Credit Reporting Act — governs credit reports and consumer data.",
    "dppa": "the Driver's Privacy Protection Act — protects DMV/driver record data.",
    "glba": "the Gramm-Leach-Bliley Act — governs how financial institutions handle personal data.",
}


def _fallback_glossary(text: str) -> List[Dict[str, str]]:
    """Detect known legal terms present in the text and return plain definitions."""
    low = text.lower()
    found: List[Dict[str, str]] = []
    for term, meaning in _GLOSSARY.items():
        # word-boundary match (handles multiword terms too).
        if re.search(r"\b" + re.escape(term) + r"\b", low):
            found.append({"term": term, "meaning": meaning})
    return found


_SYSTEM = (
    "You are a LAYMAN'S-TERMS TRANSCRIBER for L.E.A.D.S. Your job is to translate "
    "legal material into plain English a non-lawyer JUROR can understand — about "
    "an 8th-grade reading level, neutral, accurate, no condescension. Explain ONLY "
    "what the source text says; do not add outside facts or give advice. Respond "
    "with STRICT JSON (no markdown, no code fences) of EXACTLY this shape:\n"
    "{\n"
    '  "plain_transcription": "the source rewritten in plain, everyday English",\n'
    '  "overview": "1-2 sentence gist of what this is about",\n'
    '  "glossary": [{"term": "legal word/phrase", "meaning": "plain definition"}],\n'
    '  "step_by_step": ["plain bullet points walking through what happens/what it says"],\n'
    '  "why_it_matters": "why a regular person should care, in plain terms",\n'
    '  "analogy": "one short everyday analogy that captures the idea",\n'
    '  "bottom_line": "the single most important takeaway in one sentence"\n'
    "}\n"
    "Define EVERY legal term or piece of jargon that appears. Keep sentences short."
)


def explain(
    citation: Optional[str] = None,
    text: Optional[str] = None,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcribe legal material into plain English. Returns {error} if nothing resolves."""
    source = resolve_source_text(citation=citation, text=text, source_id=source_id)
    if source is None or not source.get("text"):
        return {"error": "Nothing to explain. Paste the legal text, or give a citation / "
                "corpus source_id to pull the text."}

    src_text = source["text"]
    user = (
        f"Source ({source.get('citation','') or source.get('title','text')}):\n\n"
        f"{src_text}\n\nTranscribe this into plain English as STRICT JSON."
    )
    raw, provider = llm_router.synthesize(_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None

    if not parsed:
        # Extractive fallback: still give a useful glossary + the original text.
        return {
            "title": source.get("title", ""),
            "citation": source.get("citation", ""),
            "plain_transcription": "",
            "overview": "",
            "glossary": _fallback_glossary(src_text),
            "step_by_step": [],
            "why_it_matters": "",
            "analogy": "",
            "bottom_line": "",
            "source_excerpt": src_text[:1500],
            "url": source.get("url", ""),
            "provider": provider,
            "note": "No LLM provider available — showing a plain glossary of legal terms found in "
            "the text (extractive mode). Configure an LLM key for the full plain-English transcription.",
            "disclaimer": _DISCLAIMER,
        }

    def _s(v: Any) -> str:
        return str(v).strip() if v is not None else ""

    glossary = parsed.get("glossary") or []
    norm_gloss: List[Dict[str, str]] = []
    if isinstance(glossary, list):
        for g in glossary:
            if isinstance(g, dict) and _s(g.get("term")):
                norm_gloss.append({"term": _s(g.get("term")), "meaning": _s(g.get("meaning"))})
    if not norm_gloss:
        norm_gloss = _fallback_glossary(src_text)

    steps = parsed.get("step_by_step") or []
    norm_steps = [str(s).strip() for s in steps if str(s).strip()] if isinstance(steps, list) else []

    return {
        "title": source.get("title", ""),
        "citation": source.get("citation", ""),
        "plain_transcription": _s(parsed.get("plain_transcription")),
        "overview": _s(parsed.get("overview")),
        "glossary": norm_gloss,
        "step_by_step": norm_steps,
        "why_it_matters": _s(parsed.get("why_it_matters")),
        "analogy": _s(parsed.get("analogy")),
        "bottom_line": _s(parsed.get("bottom_line")),
        "url": source.get("url", ""),
        "provider": provider,
        "note": "",
        "disclaimer": _DISCLAIMER,
    }
