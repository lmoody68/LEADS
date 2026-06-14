"""
Source Credibility Scorer (MasterBuildPlan §3.3) for L.E.A.D.S.

Applies investigative rigor to evaluate how reliable a source is, scoring it
across FIVE weighted dimensions and producing a structured, transparent
dashboard with rationale, a tier (primary vs. secondary), flags, and a
corroboration view (which OTHER corpus sources agree vs. conflict).

Scoring dimensions & weights (from §3.3):
    Authority      25%   primary authority (court/legislature) vs. secondary?
    Currency       20%   how recent; superseded/overruled?
    Corroboration  25%   can the claim be triangulated with independent sources?
    Bias/Interest  15%   does the source have a stake in the outcome?
    Completeness   15%   full context vs. key omissions?

The corroboration view retrieves OTHER sources from the seeded legal corpus via
the existing Phase-1 hybrid retrieval and has the LLM note agreement/conflict.

A Shepardize-style flag (overruled / distinguished / followed) is produced as a
clearly-labeled HEURISTIC — it is NOT an authoritative citator validation (only
a real citator like Shepard's/KeyCite can confirm a case's current status).

REUSE: `rag.hybrid_retrieve` for corroboration; `llm_router.synthesize` for
scoring. With NO LLM key, a deterministic authority/currency score is derived
from metadata, with an explicit note that full multi-dimension scoring needs an LLM.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import llm_router, rag

# Weights MUST match §3.3 and sum to 1.0.
_WEIGHTS: Dict[str, float] = {
    "Authority": 0.25,
    "Currency": 0.20,
    "Corroboration": 0.25,
    "Bias/Interest": 0.15,
    "Completeness": 0.15,
}

_CORROBORATION_K = 4


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
# Source resolution — accept a pasted source OR a source_id from the corpus.
# ---------------------------------------------------------------------------
def resolve_source(
    source_id: Optional[str],
    title: Optional[str],
    citation: Optional[str],
    text: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Resolve the source to score. Priority:
      1. If source_id is given, look it up in the legal corpus by chunk_id (the
         id rag.ingest assigns) — this lets the UI score a card from a prior result.
      2. Otherwise build a source from the pasted {title, citation, text}.
    Returns a normalized source dict, or None if nothing usable was supplied.
    """
    if source_id:
        found = _lookup_by_id(source_id)
        if found:
            return found
        # Fall through to pasted fields if the id didn't resolve.

    text = (text or "").strip()
    citation = (citation or "").strip()
    title = (title or "").strip()
    if not (text or citation or title):
        return None
    return {
        "source_title": title or (citation or "Pasted source"),
        "citation": citation,
        "snippet": text,
        "doc_type": "opinion" if _looks_like_opinion(citation, text) else "statute",
        "court": "",
        "date": "",
        "url": "",
        "legal_section": "",
    }


def _lookup_by_id(source_id: str) -> Optional[Dict[str, Any]]:
    """Look up a chunk by its chunk_id in the shared legal collection."""
    try:
        col = rag.get_collection()
        got = col.get(ids=[source_id])
        docs = got.get("documents") or []
        metas = got.get("metadatas") or []
        if docs and metas:
            meta = metas[0]
            return {
                "source_title": meta.get("source_title", ""),
                "citation": meta.get("citation", meta.get("section", "")),
                "snippet": docs[0],
                "doc_type": meta.get("doc_type", "statute"),
                "court": meta.get("court", ""),
                "date": meta.get("date", ""),
                "url": meta.get("url", ""),
                "legal_section": meta.get("legal_section", ""),
            }
    except Exception:
        pass
    return None


_OPINION_HINT_RE = re.compile(r"\bv\.\b|\d+\s+U\.?S\.?\s+\d+|\b(?:hold|held|affirm|reverse|remand)\b", re.IGNORECASE)


def _looks_like_opinion(citation: str, text: str) -> bool:
    blob = f"{citation} {text}"
    return bool(_OPINION_HINT_RE.search(blob)) and "U.S.C" not in (citation or "")


# ---------------------------------------------------------------------------
# Corroboration — pull OTHER corpus sources relevant to this one.
# ---------------------------------------------------------------------------
def _corroborating_sources(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    query = f"{source.get('citation','')} {source.get('snippet','')}".strip()
    if not query:
        return []
    hits, _debug = rag.hybrid_retrieve(query, k=_CORROBORATION_K + 1)
    own_cite = (source.get("citation") or "").strip()
    own_snip = (source.get("snippet") or "")[:60]
    out: List[Dict[str, Any]] = []
    for h in hits:
        # Skip the source itself (same citation + same opening text).
        if h.get("citation", "") == own_cite and (h.get("snippet") or "")[:60] == own_snip:
            continue
        out.append(h)
        if len(out) >= _CORROBORATION_K:
            break
    return out


# ---------------------------------------------------------------------------
# Shepardize-style HEURISTIC flag (explicitly NOT authoritative validation).
# ---------------------------------------------------------------------------
_OVERRULED_RE = re.compile(r"\b(overrul(?:e|ed|ing)|abrogat(?:e|ed)|supersed(?:e|ed))\b", re.IGNORECASE)
_DISTINGUISHED_RE = re.compile(r"\bdisting(?:uish|uished)\b", re.IGNORECASE)
_FOLLOWED_RE = re.compile(r"\b(follow(?:ed|ing)|reaffirm(?:ed)?|adher(?:e|ed) to)\b", re.IGNORECASE)


def _shepardize_heuristic(source: Dict[str, Any], corroborators: List[Dict[str, Any]]) -> str:
    """
    A CLEARLY-LABELED heuristic treatment signal based on language in the source +
    nearby corpus text. This is NOT a citator validation (Shepard's/KeyCite) — it
    only flags words like 'overruled' / 'distinguished' / 'followed' if present.
    """
    blob = source.get("snippet", "") + " " + " ".join(c.get("snippet", "") for c in corroborators)
    if _OVERRULED_RE.search(blob):
        signal = "possibly OVERRULED / superseded"
    elif _DISTINGUISHED_RE.search(blob):
        signal = "possibly DISTINGUISHED"
    elif _FOLLOWED_RE.search(blob):
        signal = "apparently FOLLOWED / reaffirmed"
    else:
        signal = "no treatment signal detected"
    return (
        f"Shepardize-style heuristic: {signal}. "
        "HEURISTIC ONLY — this is a keyword signal over the local corpus, NOT an "
        "authoritative citator (Shepard's / KeyCite) validation of the source's "
        "current legal status."
    )


# ---------------------------------------------------------------------------
# LLM scoring.
# ---------------------------------------------------------------------------
_SCORE_SYSTEM = (
    "You are the SOURCE CREDIBILITY SCORER of L.E.A.D.S., applying investigative "
    "rigor to evaluate how reliable a legal source is. Score the TARGET source "
    "across EXACTLY these five dimensions, each 0-100, using the provided weights:\n"
    "- Authority (weight 0.25): is it PRIMARY authority (court opinion, statute, "
    "regulation) or SECONDARY (law review, news, blog)? Primary scores higher.\n"
    "- Currency (weight 0.20): how recent is it; is it superseded/overruled/amended?\n"
    "- Corroboration (weight 0.25): do the OTHER provided corpus sources AGREE with "
    "it (higher) or CONFLICT (lower)? Use the corroboration passages.\n"
    "- Bias/Interest (weight 0.15): does the source have a stake/advocacy interest? "
    "Neutral primary law scores higher; advocacy/interested sources lower.\n"
    "- Completeness (weight 0.15): does it give full context or omit key qualifiers/"
    "exceptions?\n\n"
    "Also classify TIER: 'primary' (court/legislature/regulator) or 'secondary' "
    "(commentary/news/derivative). List concrete flags (e.g., 'no date metadata — "
    "currency uncertain', 'single-source — weak corroboration'). For corroboration, "
    "list which provided sources AGREE vs. CONFLICT by their citation.\n\n"
    "Respond with STRICT JSON ONLY (no markdown, no code fences) of this shape:\n"
    "{\n"
    '  "dimensions": [{"name": "Authority", "score_0_100": 0-100, "rationale": "..."}, '
    '... all five ...],\n'
    '  "tier": "primary" | "secondary",\n'
    '  "flags": ["...", "..."],\n'
    '  "corroboration": {"agreeing": ["citation — why", "..."], '
    '"conflicting": ["citation — why", "..."]}\n'
    "}\n"
    "Score honestly and conservatively. Do not invent sources beyond those provided."
)


def _score_llm(
    source: Dict[str, Any], corroborators: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    corro_block = "\n\n".join(
        f"[{i}] {c.get('source_title','')} — {c.get('citation','')}\n    {c.get('snippet','')}"
        for i, c in enumerate(corroborators, 1)
    ) or "(no other corpus sources retrieved)"
    user = (
        f"TARGET source to score:\n"
        f"  Title: {source.get('source_title','')}\n"
        f"  Citation: {source.get('citation','')}\n"
        f"  Type: {source.get('doc_type','')}\n"
        f"  Court/Date: {source.get('court','')} {source.get('date','')}\n"
        f"  Text: {source.get('snippet','')}\n\n"
        f"OTHER corpus sources for corroboration:\n{corro_block}\n\n"
        "Score the TARGET across the five weighted dimensions as STRICT JSON."
    )
    raw, provider = llm_router.synthesize(_SCORE_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None
    if not parsed:
        return None
    parsed["provider"] = provider
    return parsed


# ---------------------------------------------------------------------------
# Deterministic fallback (no LLM key) — authority/currency from metadata.
# ---------------------------------------------------------------------------
def _score_deterministic(
    source: Dict[str, Any], corroborators: List[Dict[str, Any]]
) -> Dict[str, Any]:
    doc_type = source.get("doc_type", "statute")
    is_primary = doc_type in ("statute", "opinion")
    citation = source.get("citation", "")
    text = source.get("snippet", "")

    # Authority: primary statute/opinion scores high; otherwise mid.
    authority = 90 if is_primary else 45
    auth_rationale = (
        f"Classified as PRIMARY authority ({'statute' if doc_type=='statute' else 'court opinion'})."
        if is_primary
        else "Not identifiable as primary authority from metadata — treated as secondary."
    )

    # Currency: from a parsed date if present; statutes (no date) get a neutral score.
    date = source.get("date", "")
    currency, cur_rationale = _currency_from_date(date, is_statute=(doc_type == "statute"))

    # Corroboration: count overlapping sources retrieved from the corpus.
    n_corr = len(corroborators)
    corroboration = min(40 + n_corr * 15, 85)
    corr_rationale = (
        f"{n_corr} related corpus source(s) retrieved (deterministic count; an LLM is "
        "needed to judge agreement vs. conflict)."
    )

    # Bias / Completeness: not assessable without an LLM — neutral with a note.
    bias = 70 if is_primary else 50
    completeness = 55

    dimensions = [
        {"name": "Authority", "weight": _WEIGHTS["Authority"], "score_0_100": authority, "rationale": auth_rationale},
        {"name": "Currency", "weight": _WEIGHTS["Currency"], "score_0_100": currency, "rationale": cur_rationale},
        {"name": "Corroboration", "weight": _WEIGHTS["Corroboration"], "score_0_100": corroboration, "rationale": corr_rationale},
        {"name": "Bias/Interest", "weight": _WEIGHTS["Bias/Interest"], "score_0_100": bias,
         "rationale": "Primary law is presumptively neutral; full bias assessment needs an LLM." if is_primary
         else "Bias/interest not assessable from metadata without an LLM."},
        {"name": "Completeness", "weight": _WEIGHTS["Completeness"], "score_0_100": completeness,
         "rationale": "Completeness cannot be judged without an LLM; neutral placeholder."},
    ]
    weighted = _weighted_total(dimensions)
    return {
        "dimensions": dimensions,
        "tier": "primary" if is_primary else "secondary",
        "flags": [
            "Extractive mode (no LLM key): Authority & Currency are derived from "
            "metadata; Bias/Interest & Completeness are placeholders. Configure an "
            "LLM provider for full multi-dimension scoring.",
        ] + ([] if citation else ["No citation supplied — authority is harder to verify."]),
        "corroboration": {
            "agreeing": [c.get("citation", "") for c in corroborators if c.get("citation")],
            "conflicting": [],
        },
        "weighted_total": weighted,
        "provider": "extractive (no LLM key)",
    }


def _currency_from_date(date: str, is_statute: bool) -> tuple[int, str]:
    """Heuristic currency 0-100 from a year in the date string."""
    year_match = re.search(r"(19|20)\d{2}", date or "")
    if not year_match:
        if is_statute:
            return 75, "No date metadata; statutes remain in force until amended/repealed (neutral-high)."
        return 50, "No date metadata — currency cannot be assessed (neutral)."
    year = int(year_match.group(0))
    age = max(0, datetime.utcnow().year - year)
    score = max(30, 100 - age * 2)  # ~2 points/year, floor 30
    return score, f"Dated {year} (~{age} yr old); currency scaled by age."


def _weighted_total(dimensions: List[Dict[str, Any]]) -> float:
    total = 0.0
    for d in dimensions:
        w = _WEIGHTS.get(d.get("name", ""), 0.0)
        try:
            score = float(d.get("score_0_100", 0))
        except Exception:
            score = 0.0
        total += w * max(0.0, min(100.0, score))
    return round(total, 1)


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------
def score(
    source_id: Optional[str] = None,
    title: Optional[str] = None,
    citation: Optional[str] = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Score a source's credibility across the five weighted dimensions.

    Returns:
      {
        source: {source_title, citation, doc_type, ...},
        dimensions: [{name, weight, score_0_100, rationale}],
        weighted_total: float (0-100),
        tier: "primary" | "secondary",
        flags: [...],
        corroboration: {agreeing: [...], conflicting: [...]},
        shepardize_heuristic: "... HEURISTIC ONLY ...",
        provider
      }
    """
    source = resolve_source(source_id, title, citation, text)
    if source is None:
        return {
            "error": "No source supplied. Provide a source_id from a prior result, "
            "or paste a title/citation/text to score.",
        }

    corroborators = _corroborating_sources(source)
    parsed = _score_llm(source, corroborators)

    if parsed is None:
        result = _score_deterministic(source, corroborators)
    else:
        # Normalize LLM dimensions: enforce the five names, attach the fixed weights.
        raw_dims = parsed.get("dimensions") or []
        by_name = {}
        if isinstance(raw_dims, list):
            for d in raw_dims:
                if isinstance(d, dict) and d.get("name"):
                    by_name[str(d["name"]).strip().lower()] = d
        dimensions: List[Dict[str, Any]] = []
        for name, weight in _WEIGHTS.items():
            d = by_name.get(name.lower(), {})
            try:
                sc = float(d.get("score_0_100", 50))
            except Exception:
                sc = 50.0
            dimensions.append(
                {
                    "name": name,
                    "weight": weight,
                    "score_0_100": max(0, min(100, round(sc))),
                    "rationale": str(d.get("rationale", "")).strip() or "—",
                }
            )
        corro = parsed.get("corroboration") or {}
        result = {
            "dimensions": dimensions,
            "weighted_total": _weighted_total(dimensions),
            "tier": "primary" if str(parsed.get("tier", "")).strip().lower() == "primary" else "secondary",
            "flags": [str(x).strip() for x in (parsed.get("flags") or []) if str(x).strip()],
            "corroboration": {
                "agreeing": [str(x).strip() for x in (corro.get("agreeing") or []) if str(x).strip()],
                "conflicting": [str(x).strip() for x in (corro.get("conflicting") or []) if str(x).strip()],
            },
            "provider": parsed.get("provider", "llm"),
        }

    result["source"] = {
        "source_title": source.get("source_title", ""),
        "citation": source.get("citation", ""),
        "doc_type": source.get("doc_type", ""),
        "court": source.get("court", ""),
        "date": source.get("date", ""),
        "url": source.get("url", ""),
        "legal_section": source.get("legal_section", ""),
    }
    result["shepardize_heuristic"] = _shepardize_heuristic(source, corroborators)
    return result
