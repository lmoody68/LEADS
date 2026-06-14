"""
Citator (MasterBuildPlan §3.3 enhancement) for L.E.A.D.S. — a REAL citation-
network lookup built on the CourtListener v4 API (Free Law Project), replacing
the local-corpus keyword heuristic in credibility.py with actual data:

  * VALIDATE a citation  — does "514 U.S. 291" resolve to a real, identifiable
    case?  (CourtListener citation-lookup endpoint.)
  * CITED-BY count       — how many later opinions cite this one (influence /
    "is it still being relied on").  (Derived from the cites search `count`.)
  * RECENT CITING CASES  — the most recent opinions that cite it, scanned for
    treatment language (overruled / distinguished / followed / questioned).
    (search ?type=o&q=cites:(<id>).)

This is a TRANSPARENT, best-effort citator over PUBLIC court data — NOT a
commercial validator. We still label any treatment signal as a heuristic
read of the citing opinions' language; we never assert a case is "good law"
with false authority. Shepard's / KeyCite remain the authoritative citators.

GUARDRAILS:
- PUBLIC court data via the OFFICIAL CourtListener REST API only. No scraping.
- GRACEFUL: on no token / no network / 429 / bad JSON, every function returns a
  structured "unavailable" result so the caller falls back to the local
  heuristic. Never raises.
- Auth: sends `Authorization: Token <COURTLISTENER_API_TOKEN>` when set (the
  citation-network endpoints need it); without a token it reports unavailable.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx

from . import ingest  # reuse the vetted on-disk cache helpers (rate-limit friendly)

_BASE = "https://www.courtlistener.com"
_LOOKUP_URL = f"{_BASE}/api/rest/v4/citation-lookup/"
_SEARCH_URL = f"{_BASE}/api/rest/v4/search/"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_USER_AGENT = "L.E.A.D.S./1.2 (legal-research portfolio app; contact lesliemoody68@yahoo.com)"

# Treatment-language signals scanned in the names/snippets of CITING opinions.
_NEGATIVE_RE = re.compile(r"\b(overrul(?:e|ed|ing)|abrogat(?:e|ed|ing)|supersed(?:e|ed)|vacat(?:e|ed))\b", re.IGNORECASE)
_DISTINGUISH_RE = re.compile(r"\bdisting(?:uish|uished|uishing)\b", re.IGNORECASE)
_QUESTION_RE = re.compile(r"\b(question(?:ed|ing)?|criticiz(?:e|ed)|declin(?:e|ed) to follow|call(?:ed|s) into doubt)\b", re.IGNORECASE)
_FOLLOW_RE = re.compile(r"\b(follow(?:ed|ing)?|reaffirm(?:ed|ing)?|adher(?:e|ed|ing) to|appl(?:y|ied|ying))\b", re.IGNORECASE)


def has_token() -> bool:
    return bool(os.getenv("COURTLISTENER_API_TOKEN"))


def _headers() -> Dict[str, str]:
    h = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    tok = os.getenv("COURTLISTENER_API_TOKEN")
    if tok:
        h["Authorization"] = f"Token {tok.strip()}"
    return h


def _unavailable(reason: str, citation: str = "") -> Dict[str, Any]:
    return {
        "available": False,
        "citation": citation,
        "reason": reason,
        "validated": None,
        "cited_by_count": None,
        "citing_cases": [],
        "treatment": "Citator unavailable — falling back to the local keyword heuristic.",
        "source": "CourtListener API",
    }


def _opinion_ids_from_cluster(cluster: Dict[str, Any]) -> List[str]:
    """
    All sub_opinion ids for a cluster. A cluster can hold several opinions
    (majority + concurrence + dissent); later courts may cite ANY of them, so
    we collect every id and OR them in the cites query (picking just one — e.g.
    a dissent — under-counts or zeroes out the citation network).
    """
    ids: List[str] = []
    for sub in (cluster.get("sub_opinions") or []):
        m = re.search(r"/(\d+)/?$", str(sub).rstrip("/"))
        if m:
            ids.append(m.group(1))
    return ids[:6]  # keep the cites query bounded


def _resolve_count(client: httpx.Client, payload: Dict[str, Any]) -> Optional[int]:
    """
    CourtListener v4 uses DEFERRED counts: the list `count` field is a URL you
    GET to obtain the integer. Resolve it (best-effort).
    """
    count = payload.get("count")
    if isinstance(count, int):
        return count
    if isinstance(count, str) and count.startswith("http"):
        try:
            r = client.get(count, headers=_headers(), timeout=_TIMEOUT)
            if r.status_code == 200:
                val = r.json().get("count")
                return int(val) if isinstance(val, (int, float)) else None
        except Exception:
            return None
    return None


def _treatment(cited_by_count: Optional[int], citing_cases: List[Dict[str, Any]]) -> str:
    """
    Derive a TRANSPARENT treatment read from real citation data: the cited-by
    count (influence) plus a keyword scan of recent citing opinions' names/
    snippets. Always labeled as a heuristic, never an authoritative validation.
    """
    blob = " ".join(
        f"{c.get('case_name','')} {c.get('snippet','')}" for c in citing_cases
    )
    if _NEGATIVE_RE.search(blob):
        signal = "⚠ NEGATIVE treatment language detected in a citing opinion (possible overruled/superseded/vacated)"
    elif _QUESTION_RE.search(blob):
        signal = "⚠ a citing opinion appears to QUESTION/CRITICIZE this authority"
    elif _DISTINGUISH_RE.search(blob):
        signal = "a citing opinion DISTINGUISHES this authority"
    elif _FOLLOW_RE.search(blob):
        signal = "recent citing opinions appear to FOLLOW/apply this authority"
    elif cited_by_count and cited_by_count > 0:
        signal = "cited by later opinions (no explicit treatment language detected in the sample)"
    else:
        signal = "no citing opinions found in CourtListener"

    influence = ""
    if isinstance(cited_by_count, int):
        if cited_by_count >= 100:
            influence = f" Heavily cited ({cited_by_count} citing opinions) — a frequently-relied-on authority."
        elif cited_by_count > 0:
            influence = f" Cited by {cited_by_count} opinion(s)."
        else:
            influence = " No later citing opinions on record."
    return (
        f"Citation-network read: {signal}.{influence} "
        "The treatment scan covers only the MOST RECENT citing opinions, so an old "
        "overruling (e.g. a decades-ago reversal) may not appear here. HEURISTIC over "
        "PUBLIC CourtListener citation data — a real-data signal, but NOT an "
        "authoritative citator (Shepard's / KeyCite) validation. Always verify a "
        "case's current status before relying on it."
    )


def treatment_for_citation(citation: str, max_citing: int = 5) -> Dict[str, Any]:
    """
    Look up a citation in CourtListener and return a real citation-network
    treatment report:
      {available, citation, validated:{case_name,date,court,url,cluster_id},
       cited_by_count, citing_cases:[{case_name,date,citation,url,snippet}],
       treatment, source}
    Returns an 'unavailable' report (never raises) on any failure so the caller
    can fall back to the local heuristic.
    """
    citation = (citation or "").strip()
    if not citation:
        return _unavailable("no citation supplied")
    if not has_token():
        return _unavailable("no COURTLISTENER_API_TOKEN configured", citation)

    # Cache successful reports on disk so repeat checks (and the credibility
    # scorer reusing this) don't re-hit CourtListener's rate-limited API.
    cache_key = f"citator::{citation.lower()}"
    cached = ingest._cache_get(cache_key)
    if isinstance(cached, dict) and cached.get("available"):
        return cached

    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            # 1. Validate / resolve the citation.
            resp = client.post(_LOOKUP_URL, headers=_headers(), data={"text": citation})
            if resp.status_code == 429:
                return _unavailable("rate-limited (HTTP 429) — backed off", citation)
            if resp.status_code != 200:
                return _unavailable(f"citation-lookup HTTP {resp.status_code}", citation)
            items = resp.json()
            if not isinstance(items, list) or not items:
                return _unavailable("citation not recognized", citation)

            # First item with a resolved cluster.
            resolved = None
            for it in items:
                if it.get("status") == 200 and (it.get("clusters") or []):
                    resolved = it
                    break
            if not resolved:
                return {
                    **_unavailable("citation did not resolve to a known case", citation),
                    "available": True,
                    "validated": False,
                    "treatment": "Citation NOT FOUND in CourtListener — it may be mis-cited, "
                                 "unpublished, or outside CourtListener's coverage. Verify the cite.",
                }

            cluster = (resolved.get("clusters") or [{}])[0]
            cluster_id = cluster.get("id")
            case_name = cluster.get("case_name") or cluster.get("caseName") or "Unknown case"
            abs_url = cluster.get("absolute_url") or ""
            validated = {
                "case_name": case_name,
                "date": cluster.get("date_filed") or "",
                "court": cluster.get("court_id") or cluster.get("court") or "",
                "url": (_BASE + abs_url) if abs_url.startswith("/") else abs_url,
                "cluster_id": cluster_id,
                "normalized": resolved.get("normalized_citations") or [resolved.get("citation")],
            }

            op_ids = _opinion_ids_from_cluster(cluster)

            # 2. ONE search for opinions citing this one: it yields BOTH the
            # cited-by count (the search `count` field) AND the recent citing
            # cases — so we avoid extra calls and stay under CourtListener's
            # rate limit. (Replaces a separate opinions-cited + count request.)
            # OR across every sub-opinion id so multi-opinion clusters (majority
            # + dissent) aren't under-counted.
            cited_by_count = None
            citing_cases: List[Dict[str, Any]] = []
            if op_ids:
                cites_q = " OR ".join(f"cites:({i})" for i in op_ids)
                sr = client.get(_SEARCH_URL, headers=_headers(),
                                params={"type": "o", "q": cites_q, "order_by": "dateFiled desc"})
                if sr.status_code == 200:
                    payload = sr.json()
                    cited_by_count = _resolve_count(client, payload)
                    for r in (payload.get("results") or [])[:max_citing]:
                        cites = r.get("citation")
                        cite_str = cites[0] if isinstance(cites, list) and cites else (cites or "")
                        opinions = r.get("opinions") or []
                        snippet = (opinions[0].get("snippet") if opinions and isinstance(opinions[0], dict) else "") or ""
                        cabs = r.get("absolute_url") or ""
                        citing_cases.append(
                            {
                                "case_name": r.get("caseName") or "Unknown",
                                "date": r.get("dateFiled") or "",
                                "citation": cite_str,
                                "url": (_BASE + cabs) if cabs.startswith("/") else cabs,
                                "snippet": re.sub(r"<[^>]+>", "", snippet)[:300],
                            }
                        )

            report = {
                "available": True,
                "citation": citation,
                "validated": validated,
                "cited_by_count": cited_by_count,
                "citing_cases": citing_cases,
                "treatment": _treatment(cited_by_count, citing_cases),
                "source": "CourtListener API (Free Law Project)",
            }
            # Only cache a COMPLETE report (the cites-search succeeded). Caching
            # a partial result whose cited-by lookup was transiently rate-limited
            # would poison future checks, so leave those uncached to retry later.
            if cited_by_count is not None:
                ingest._cache_put(cache_key, report)
            return report
    except Exception as exc:
        return _unavailable(f"error: {exc}", citation)
