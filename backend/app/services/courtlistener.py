"""
CourtListener integration (MasterBuildPlan §3.1, §5) for L.E.A.D.S.

Queries the CourtListener v4 REST API opinion search for relevant court
opinions, fetches their plain text, and normalizes each to a uniform shape so
the RAG pipeline can ingest live case law on-demand alongside the seeded
statutes.

GUARDRAILS (NON-NEGOTIABLE):
- PUBLIC legal data ONLY. CourtListener is a free, public database of U.S. court
  opinions (Free Law Project). We use its official REST API — NO scraping.
- No PII harvesting. We fetch published judicial opinions, nothing else.
- Nothing trains on the data — opinions are cached LOCALLY (backend/.cache) only
  to avoid re-fetching and respect rate limits, never published.
- GRACEFUL by design: on ANY error (no network, HTTP 429 rate-limit, bad JSON),
  every function returns [] / None and logs a note. The pipeline must still
  answer from the seeded statute corpus.

Auth: if COURTLISTENER_API_TOKEN is set we send `Authorization: Token <t>`
(higher rate limits). Otherwise we query anonymously (which CourtListener
heavily rate-limits — hence the graceful 429 fallback + local cache).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
CACHE_DIR = Path(os.getenv("COURTLISTENER_CACHE_DIR", str(_BACKEND_ROOT / ".cache" / "courtlistener")))

_BASE = "https://www.courtlistener.com"
_SEARCH_URL = f"{_BASE}/api/rest/v4/search/"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_USER_AGENT = "L.E.A.D.S./0.2 (legal-research portfolio app; contact lesliemoody68@yahoo.com)"


# --- Status / availability ---------------------------------------------------
def has_token() -> bool:
    return bool(os.getenv("COURTLISTENER_API_TOKEN"))


def availability() -> Dict[str, Any]:
    """Lightweight description of CourtListener access for /api/health."""
    return {
        "configured": True,  # the integration is always present
        "auth": "token" if has_token() else "anonymous (rate-limited)",
    }


def _headers() -> Dict[str, str]:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    token = os.getenv("COURTLISTENER_API_TOKEN")
    if token:
        headers["Authorization"] = f"Token {token.strip()}"
    return headers


# --- Local cache -------------------------------------------------------------
def _cache_path(key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / f"{digest}.json"


def _cache_get(key: str) -> Optional[Any]:
    path = _cache_path(key)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_put(key: str, value: Any) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(json.dumps(value), encoding="utf-8")
    except Exception:
        # Caching is best-effort; never let it break the pipeline.
        pass


# --- HTTP helper (graceful) --------------------------------------------------
def _get_json(client: httpx.Client, url: str) -> Optional[Any]:
    """GET a URL and return parsed JSON, or None on any error / rate-limit."""
    try:
        resp = client.get(url, headers=_headers(), timeout=_TIMEOUT, follow_redirects=True)
    except Exception as exc:  # no network, DNS, timeout, etc.
        print(f"[CourtListener] request failed for {url}: {exc}")
        return None
    if resp.status_code == 429:
        print(f"[CourtListener] HTTP 429 rate-limited ({'token' if has_token() else 'anonymous'}). "
              f"Falling back to seeded corpus.")
        return None
    if resp.status_code != 200:
        print(f"[CourtListener] HTTP {resp.status_code} for {url}: falling back gracefully.")
        return None
    try:
        return resp.json()
    except Exception as exc:
        print(f"[CourtListener] bad JSON from {url}: {exc}")
        return None


# --- Text cleanup ------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)  # strip HTML if the opinion came as html
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#xa7;", "§")
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def _abs_url(path_or_url: str) -> str:
    if not path_or_url:
        return ""
    if path_or_url.startswith("http"):
        return path_or_url
    return f"{_BASE}{path_or_url}"


def _best_opinion_text(op: Dict[str, Any]) -> str:
    """Pick the richest available text field from an opinion record."""
    for field in ("plain_text", "html_with_citations", "html", "html_lawbox", "html_columbia", "xml_harvard"):
        val = op.get(field)
        if val and val.strip():
            return _clean(val)
    return ""


# --- Public: search + fetch --------------------------------------------------
def search_opinions(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Search CourtListener opinions and return up to `max_results` normalized
    opinions with full text:
        {case_name, citation, court, date, url, text}

    Always returns a list. On any failure returns [] so the caller (rag.answer)
    falls back to the seeded statute corpus.
    """
    query = (query or "").strip()
    if not query:
        return []

    cache_key = f"search::{query}::{max_results}::{'tok' if has_token() else 'anon'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    params = httpx.QueryParams({"type": "o", "q": query, "order_by": "score desc"})
    search_url = f"{_SEARCH_URL}?{params}"

    results: List[Dict[str, Any]] = []
    with httpx.Client() as client:
        data = _get_json(client, search_url)
        if not data:
            return []
        clusters = data.get("results", []) or []
        for cluster in clusters[: max_results * 2]:  # over-fetch; some may have no text
            normalized = _normalize_cluster(client, cluster)
            if normalized and normalized.get("text"):
                results.append(normalized)
            if len(results) >= max_results:
                break

    # Cache even an empty list briefly? No — only cache non-empty so a transient
    # rate-limit doesn't poison future (authenticated) runs.
    if results:
        _cache_put(cache_key, results)
    return results


def _normalize_cluster(client: httpx.Client, cluster: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize a v4 search result (cluster-shaped) into our uniform opinion dict,
    fetching the opinion plain text from the nested opinion endpoint.
    """
    case_name = (
        cluster.get("caseName")
        or cluster.get("caseNameFull")
        or cluster.get("case_name")
        or "Unknown case"
    )
    court = cluster.get("court") or cluster.get("court_id") or ""
    date = cluster.get("dateFiled") or cluster.get("date_filed") or ""

    # Citation: v4 search returns a `citation` list of strings sometimes.
    citation = ""
    cites = cluster.get("citation")
    if isinstance(cites, list) and cites:
        citation = cites[0]
    elif isinstance(cites, str):
        citation = cites

    # Absolute URL to the human-readable case page on courtlistener.com.
    abs_url = _abs_url(cluster.get("absolute_url", ""))

    # The v4 search result nests per-opinion entries under "opinions"; each has
    # an "id" we can resolve to the full opinion text. Some payloads inline
    # snippet text already.
    text = ""
    op_entries = cluster.get("opinions") or []
    for entry in op_entries:
        op_id = entry.get("id") or entry.get("opinion_id")
        # Some search payloads inline a snippet — use it as a floor.
        snippet = entry.get("snippet") or ""
        if op_id:
            op_text = _fetch_opinion_text(client, op_id)
            if op_text:
                text = op_text
                break
        if snippet and not text:
            text = _clean(snippet)

    if not text:
        # Last resort: a top-level snippet on the cluster.
        text = _clean(cluster.get("snippet", ""))

    if not abs_url and op_entries:
        first = op_entries[0]
        if first.get("id"):
            abs_url = f"{_BASE}/opinion/{first['id']}/"

    return {
        "case_name": case_name,
        "citation": citation or case_name,
        "court": court,
        "date": date,
        "url": abs_url,
        "text": text,
    }


def fetch_opinion_by_citation(citation: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a citation to the CORRECT case via CourtListener's citation-lookup
    endpoint — authoritative because it matches the reporter cite itself (e.g.
    "514 U.S. 291"), NOT a free-text search that can return a same-named-but-
    different case. Then fetch that opinion's text. Returns the normalized
    opinion dict {case_name, citation, court, date, url, text}, or None
    gracefully (no token / not recognized / 429 / any error).
    """
    citation = (citation or "").strip()
    if not citation or not has_token():
        return None
    try:
        with httpx.Client() as client:
            resp = client.post(
                f"{_BASE}/api/rest/v4/citation-lookup/",
                headers=_headers(),
                data={"text": citation},
                timeout=_TIMEOUT,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return None
            items = resp.json()
            if not isinstance(items, list):
                return None
            resolved = next(
                (it for it in items if it.get("status") == 200 and (it.get("clusters") or [])),
                None,
            )
            if not resolved:
                return None
            cluster = resolved["clusters"][0]
            op_id = None
            for sub in (cluster.get("sub_opinions") or []):
                m = re.search(r"/(\d+)/?$", str(sub).rstrip("/"))
                if m:
                    op_id = m.group(1)  # last sub-opinion = lead opinion
            text = _fetch_opinion_text(client, op_id) if op_id else ""
            if not text:
                return None
            return {
                "case_name": cluster.get("case_name") or "Court opinion",
                "citation": resolved.get("citation") or citation,
                "court": cluster.get("court_id") or "",
                "date": cluster.get("date_filed") or "",
                "url": _abs_url(cluster.get("absolute_url", "")),
                "text": text,
            }
    except Exception as exc:
        print(f"[CourtListener] citation-lookup resolve failed for {citation}: {exc}")
        return None


def _fetch_opinion_text(client: httpx.Client, opinion_id: Any) -> str:
    """Fetch a single opinion's plain text by id, with local caching."""
    cache_key = f"opinion::{opinion_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached.get("text", "") if isinstance(cached, dict) else ""

    url = f"{_BASE}/api/rest/v4/opinions/{opinion_id}/"
    data = _get_json(client, url)
    if not data:
        return ""
    text = _best_opinion_text(data)
    if text:
        _cache_put(cache_key, {"text": text})
    return text
