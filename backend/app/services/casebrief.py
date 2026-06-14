"""
AI Case-Brief (IRAC) analyzer (MasterBuildPlan §3 enhancement) for L.E.A.D.S.

Turns a court opinion (resolved from a citation, pasted text, or a corpus
source_id) into a structured CASE BRIEF — the classic law-school IRAC format:
facts, procedural history, Issue(s), Rule, Analysis/Application, Holding,
disposition, key quotes, and a one-paragraph synopsis. Serves the research
workflow (quick read of a case) and the tutor (teaching how to brief a case).

Also exposes `resolve_source_text()` — the shared resolver reused by the
plain-language explainer (plainlang.py).

GUARDRAILS: public legal text only (CourtListener opinions / seeded corpus /
user-pasted text); stateless LLM calls (nothing trains on the data); graceful
extractive fallback with no LLM key. "General legal information, not legal advice."
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from . import courtlistener, llm_router, rag


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    if not fenced:
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = brace.group(0) if brace else candidate
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shared source resolver (reused by plainlang.py).
# ---------------------------------------------------------------------------
def resolve_source_text(
    citation: Optional[str] = None,
    text: Optional[str] = None,
    source_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve the material to analyze into {title, citation, text, url, doc_type}.
    Priority: pasted text > corpus source_id > citation (CourtListener, then a
    hybrid-retrieval fallback over the seeded corpus). Returns None if nothing
    usable resolves.
    """
    text = (text or "").strip()
    if text:
        return {"title": "Pasted text", "citation": (citation or "").strip(),
                "text": text[:40000], "url": "", "doc_type": "text"}

    if source_id:
        try:
            got = rag.get_collection().get(ids=[source_id])
            docs = got.get("documents") or []
            metas = got.get("metadatas") or []
            if docs:
                meta = metas[0] if metas else {}
                return {
                    "title": meta.get("source_title", ""),
                    "citation": meta.get("citation", meta.get("section", "")),
                    "text": docs[0][:40000],
                    "url": meta.get("url", ""),
                    "doc_type": meta.get("doc_type", "statute"),
                }
        except Exception:
            pass

    citation = (citation or "").strip()
    if citation:
        looks_like_case = bool(re.search(r"\bv\.?\b", citation.split(",")[0]))
        # AUTHORITATIVE: resolve via CourtListener citation-lookup first — it
        # matches the reporter cite exactly, so it can't return a same-named-but-
        # different case the way a free-text search can.
        resolved = courtlistener.fetch_opinion_by_citation(citation)
        if resolved and resolved.get("text"):
            return {"title": resolved.get("case_name", citation), "citation": resolved.get("citation", citation),
                    "text": resolved["text"][:40000], "url": resolved.get("url", ""), "doc_type": "opinion"}
        # Fallback: free-text search with a case-name overlap guard.
        try:
            ops = courtlistener.search_opinions(citation, max_results=1)
            if ops and ops[0].get("text"):
                op = ops[0]
                # GUARD: CourtListener treats the citation as a free-text search and
                # returns a best-effort top hit, so a wrong/bogus citation can match an
                # UNRELATED real case. When the input carries a case name, require it to
                # actually overlap the returned case before accepting it — otherwise we
                # would confidently brief the wrong case (a grounding hazard).
                if _citation_matches(citation, op):
                    return {"title": op.get("case_name", citation), "citation": op.get("citation", citation),
                            "text": op["text"][:40000], "url": op.get("url", ""), "doc_type": "opinion"}
                # Named case that didn't match the top hit — don't substitute a wrong case.
                if looks_like_case:
                    return None
        except Exception:
            pass
        # Fallback: best matching passage already in the corpus (for statute/other
        # references, not named cases — we don't pass a named case off as a statute).
        if not looks_like_case:
            try:
                hits, _dbg = rag.hybrid_retrieve(citation, k=1)
                if hits:
                    h = hits[0]
                    return {"title": h.get("source_title", citation), "citation": h.get("citation", citation),
                            "text": h.get("snippet", "")[:40000], "url": h.get("url", ""),
                            "doc_type": h.get("doc_type", "statute")}
            except Exception:
                pass
    return None


_NAME_STOP = {"the", "and", "for", "inc", "llc", "co", "corp", "et", "al", "in", "re", "of"}


def _citation_matches(query: str, op: Dict[str, Any]) -> bool:
    """
    True if the returned opinion plausibly matches the requested citation. When
    the query has a case name (contains 'v.'), require >=50% of its name tokens
    to appear in the returned case_name; a bare reporter cite (no name) is trusted
    (CourtListener's citation search is reliable for those).
    """
    name_part = query.split(",")[0]
    if not re.search(r"\bv\.?\b", name_part):
        return True  # bare citation, no name to verify against
    q_tokens = {t for t in re.findall(r"[a-z]{3,}", name_part.lower())} - _NAME_STOP
    if not q_tokens:
        return True
    op_tokens = set(re.findall(r"[a-z]{3,}", (op.get("case_name") or "").lower()))
    overlap = len(q_tokens & op_tokens) / len(q_tokens)
    return overlap >= 0.5


_DISCLAIMER = "General legal information, not legal advice. AI-generated from the source text — verify against the full opinion."

_BRIEF_SYSTEM = (
    "You are a legal research assistant writing a CASE BRIEF in IRAC form. Using "
    "ONLY the provided case text, produce STRICT JSON (no markdown, no code "
    "fences) of EXACTLY this shape:\n"
    "{\n"
    '  "case_name": "...",\n'
    '  "citation": "...",\n'
    '  "facts": "concise material facts",\n'
    '  "procedural_history": "how the case got here (or empty)",\n'
    '  "issues": ["the legal question(s) presented"],\n'
    '  "rule": "the governing rule/legal standard the court applied",\n'
    '  "analysis": "how the court applied the rule to the facts (the reasoning)",\n'
    '  "holding": "the court\'s answer to the issue",\n'
    '  "disposition": "affirmed/reversed/remanded/etc. (or empty)",\n'
    '  "key_quotes": ["short verbatim quotes from the text"],\n'
    '  "synopsis": "one-paragraph plain summary of what the case decided"\n'
    "}\n"
    "Be accurate and grounded ONLY in the provided text. If something is not in "
    "the text, use an empty string or empty list — never invent facts, holdings, "
    "or citations."
)


def _empty_brief(source: Dict[str, Any], note: str, provider: str) -> Dict[str, Any]:
    return {
        "case_name": source.get("title", ""),
        "citation": source.get("citation", ""),
        "facts": "", "procedural_history": "", "issues": [], "rule": "",
        "analysis": "", "holding": "", "disposition": "", "key_quotes": [],
        "synopsis": "", "source_excerpt": source.get("text", "")[:1500],
        "url": source.get("url", ""), "provider": provider, "note": note,
        "disclaimer": _DISCLAIMER,
    }


def brief(
    citation: Optional[str] = None,
    text: Optional[str] = None,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Produce a structured IRAC case brief. Returns {error} if nothing resolves."""
    source = resolve_source_text(citation=citation, text=text, source_id=source_id)
    if source is None or not source.get("text"):
        return {"error": "Could not find the case. Paste the opinion text, give a citation "
                "(e.g. 'Heintz v. Jenkins, 514 U.S. 291'), or a corpus source_id."}

    user = (
        f"Case citation (if known): {source.get('citation','')}\n"
        f"Case title (if known): {source.get('title','')}\n\n"
        f"CASE TEXT:\n{source['text']}\n\n"
        "Write the IRAC case brief as STRICT JSON."
    )
    raw, provider = llm_router.synthesize(_BRIEF_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None
    if not parsed:
        return _empty_brief(
            source,
            "No LLM provider available — showing the source excerpt only (extractive mode). "
            "Configure an LLM key for the full IRAC brief.",
            provider,
        )

    def _s(v: Any) -> str:
        return str(v).strip() if v is not None else ""

    def _list(v: Any) -> list:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return [str(v).strip()] if v else []

    return {
        "case_name": _s(parsed.get("case_name")) or source.get("title", ""),
        "citation": _s(parsed.get("citation")) or source.get("citation", ""),
        "facts": _s(parsed.get("facts")),
        "procedural_history": _s(parsed.get("procedural_history")),
        "issues": _list(parsed.get("issues")),
        "rule": _s(parsed.get("rule")),
        "analysis": _s(parsed.get("analysis")),
        "holding": _s(parsed.get("holding")),
        "disposition": _s(parsed.get("disposition")),
        "key_quotes": _list(parsed.get("key_quotes")),
        "synopsis": _s(parsed.get("synopsis")),
        "url": source.get("url", ""),
        "provider": provider,
        "note": "",
        "disclaimer": _DISCLAIMER,
    }
