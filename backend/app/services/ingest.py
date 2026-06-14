"""
Automated Public-Legal-Data Ingestion (MasterBuildPlan §3.8 / Phase 7) for
L.E.A.D.S. — Corpus Expansion connectors.

=============================================================================
GUARDRAILS — THIS FEATURE IS GUARDRAIL-CRITICAL. READ BEFORE EDITING.
=============================================================================
This service grows the legal corpus ONLY from official, public, and licensed
legal-data sources. The following rules are NON-NEGOTIABLE:

  * OFFICIAL APIs / BULK DOWNLOADS ONLY. We fetch exclusively through documented
    public APIs (CourtListener v4 REST API; govinfo.gov api.govinfo.gov) or
    their official bulk-download endpoints. We send an HONEST User-Agent, use
    sane rate limits + timeouts, and respect robots.txt / Terms of Service.

  * NO EVASION OF ANY KIND. There is no bot-protection bypass, no CAPTCHA
    solving, no rate-limit / IP / proxy rotation, no "stealth" scraping, and no
    fetching of any site that forbids automated access. If a source rate-limits
    us (e.g. HTTP 429) we BACK OFF and fall back gracefully — we never try to
    circumvent it. No SerpAPI-style "bypass" services.

  * PUBLIC / LICENSED LEGAL DATA ONLY. We ingest published statutes, regulations,
    public laws, and judicial opinions — public legal text. We DO NOT ingest
    people-search data, PII datasets, or any personal-data source. If a candidate
    source looks like it concerns people / personal data, it is SKIPPED and
    flagged (see dataset_discovery.py for the discovery-side PII filter).

  * EVERYTHING STAYS LOCAL. Fetched text is embedded into the LOCAL ChromaDB
    corpus the RAG already uses, and raw fetches are cached to backend/.cache/
    to respect upstream rate limits. Nothing is published; nothing trains on it.

  * IDEMPOTENT + DEDUPED. Ingestion is keyed by citation / source id so the same
    opinion or statute is never double-ingested.
=============================================================================

Sources (ALL official APIs — see note on each):
  - CourtListener v4 API (Free Law Project) — case law. Token from
    COURTLISTENER_API_TOKEN if set, else anonymous (rate-limited) search.
    NOTE: The Caselaw Access Project (CAP) API has sunset; its bulk case-law data
    now lives in CourtListener and as STATIC bulk files at static.case.law. We
    use the CourtListener API as the case-law path. static.case.law is referenced
    only as an official bulk option — we do NOT scrape it here.
  - govinfo.gov API (api.govinfo.gov) — U.S. Code / CFR / public-law / bill text.
    Uses a free api.data.gov key (GOVINFO_API_KEY / DATA_GOV_API_KEY); falls back
    to the rate-limited DEMO_KEY if unset.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from . import courtlistener, rag

# --- Paths / cache -----------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
_CACHE_DIR = Path(os.getenv("INGEST_CACHE_DIR", str(_BACKEND_ROOT / ".cache" / "ingest")))

# Honest, identifiable User-Agent (guardrail: no spoofing/stealth).
_USER_AGENT = "L.E.A.D.S./1.1 (legal-research portfolio app; contact lesliemoody68@yahoo.com)"
_TIMEOUT = httpx.Timeout(45.0, connect=10.0)

# Polite pacing between successive upstream fetches (seconds) — sane rate limit.
_POLITE_DELAY = float(os.getenv("INGEST_POLITE_DELAY", "0.4"))

# --- Last-ingest status (process-local, for /api/ingest/status) --------------
_LAST_INGEST: Optional[Dict[str, Any]] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cache_path(key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return _CACHE_DIR / f"{digest}.json"


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
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(json.dumps(value), encoding="utf-8")
    except Exception:
        pass  # caching is best-effort; never break ingestion


# --- Corpus dedupe -----------------------------------------------------------
def _existing_source_keys() -> set[str]:
    """
    Collect the dedupe keys already present in the shared legal collection.

    A dedupe key is the normalized citation (preferred) or, failing that, the
    source URL. We read the collection's metadatas once and build the set so a
    re-ingest of the same opinion/statute is skipped (idempotent).
    """
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    keys: set[str] = set()
    try:
        got = col.get(include=["metadatas"])
    except Exception:
        return keys
    for meta in (got.get("metadatas") or []):
        if not meta:
            continue
        for field in ("citation", "url", "source_title"):
            val = (meta.get(field) or "").strip()
            if val:
                keys.add(_norm_key(val))
    return keys


def _norm_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


# Redact secrets (api_key / api-key / token) from any URL before it is logged,
# so a real api.data.gov key embedded in a query string never reaches stdout.
_SECRET_QS_RE = re.compile(r"((?:api[-_]?key|token)=)[^&\s]+", re.IGNORECASE)


def _redact(url: str) -> str:
    return _SECRET_QS_RE.sub(r"\1***", url or "")


# --- HTTP helper (graceful, honest) -----------------------------------------
def _get(client: httpx.Client, url: str, *, kind: str = "GET", json_body: Any = None) -> Optional[httpx.Response]:
    """
    Polite GET/POST. Returns the Response, or None on error / rate-limit (429).

    GUARDRAIL: on 429 we BACK OFF and return None (graceful) — we never retry-
    hammer or attempt to evade the limit. Any api_key/token in the URL is
    REDACTED before logging.
    """
    try:
        time.sleep(_POLITE_DELAY)
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        if kind == "POST":
            resp = client.post(url, headers=headers, json=json_body, timeout=_TIMEOUT, follow_redirects=True)
        else:
            resp = client.get(url, headers=headers, timeout=_TIMEOUT, follow_redirects=True)
    except Exception as exc:
        print(f"[ingest] request failed for {_redact(url)}: {exc}")
        return None
    if resp.status_code == 429:
        print(f"[ingest] HTTP 429 rate-limited at {_redact(url)} — backing off gracefully (no evasion).")
        return None
    if resp.status_code != 200:
        print(f"[ingest] HTTP {resp.status_code} for {_redact(url)}: skipping gracefully.")
        return None
    return resp


# --- Text cleanup ------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .replace("&#xa7;", "§")
        .replace("&sect;", "§")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


# =============================================================================
# CourtListener connector — bulk top-N opinions for a query/jurisdiction
# =============================================================================
def ingest_courtlistener(query: str, jurisdiction: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
    """
    Bulk-ingest the top-N CourtListener opinions for `query` (optionally scoped to
    a `jurisdiction` court id, e.g. 'ca9', 'scotus') into the shared RAG corpus.

    Reuses the existing courtlistener client (official v4 API). Dedupes by
    citation/url so re-running is idempotent.

    Returns {source, query, jurisdiction, added, skipped_dupes,
             corpus_size_before, corpus_size_after, ingested}.
    """
    limit = max(1, min(int(limit or 5), 25))
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    existing = _existing_source_keys()

    # Scope to a jurisdiction by appending a court filter to the free-text query;
    # CourtListener's search honors `court:<id>` syntax in the q parameter.
    search_query = query.strip()
    if jurisdiction:
        search_query = f"{search_query} court:{jurisdiction.strip()}"

    opinions = courtlistener.search_opinions(search_query, max_results=limit)

    added = 0
    skipped = 0
    ingested_meta: List[Dict[str, Any]] = []
    new_docs: List[Dict[str, Any]] = []

    for op in opinions:
        citation = (op.get("citation") or op.get("case_name") or "").strip()
        url = (op.get("url") or "").strip()
        key = _norm_key(citation) or _norm_key(url)
        text = (op.get("text") or "")[:40000]
        if not text.strip():
            skipped += 1
            continue
        if key and key in existing:
            skipped += 1
            continue
        existing.add(key)
        new_docs.append(
            {
                "id": "cl_" + re.sub(r"[^a-zA-Z0-9]+", "_", (url or citation or "op"))[:60],
                "source_title": op.get("case_name", "Court opinion"),
                "citation": citation or op.get("case_name", ""),
                "section": citation or op.get("case_name", ""),
                "doc_type": "opinion",
                "court": op.get("court", ""),
                "date": op.get("date", ""),
                "url": url,
                "text": text,
            }
        )
        ingested_meta.append(
            {
                "case_name": op.get("case_name", ""),
                "citation": citation,
                "court": op.get("court", ""),
                "date": op.get("date", ""),
                "url": url,
            }
        )

    if new_docs:
        rag.ingest(new_docs, rag.LEGAL_COLLECTION)
        added = len(new_docs)

    size_after = col.count()
    result = {
        "source": "courtlistener",
        "query": query,
        "jurisdiction": jurisdiction or "",
        "added": added,
        "skipped_dupes": skipped,
        "corpus_size_before": size_before,
        "corpus_size_after": size_after,
        "ingested": ingested_meta,
    }
    _record_last(result)
    return result


# =============================================================================
# govinfo connector — U.S. Code / CFR / public-law / bill text by query or
# collection (official api.govinfo.gov API)
# =============================================================================
_GOVINFO_BASE = "https://api.govinfo.gov"


def _govinfo_key() -> str:
    """
    Resolve the api.data.gov key for govinfo. Honest fallback to DEMO_KEY (which
    is heavily rate-limited) when no real key is configured — noted in the
    response so the user knows to set GOVINFO_API_KEY / DATA_GOV_API_KEY.
    """
    return (os.getenv("GOVINFO_API_KEY") or os.getenv("DATA_GOV_API_KEY") or "DEMO_KEY").strip()


def _govinfo_fetch_text(client: httpx.Client, package_id: str) -> str:
    """Fetch a govinfo package's text (htm preferred, txt fallback), cached."""
    cache_key = f"govinfo_text::{package_id}"
    cached = _cache_get(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cached.get("text", "")

    key = _govinfo_key()
    text = ""
    for fmt in ("htm", "txt"):
        resp = _get(client, f"{_GOVINFO_BASE}/packages/{package_id}/{fmt}?api_key={key}")
        if resp is not None and resp.text.strip():
            text = _clean(resp.text)
            if text:
                break
    if text:
        _cache_put(cache_key, {"text": text})
    return text


def ingest_govinfo(
    query: Optional[str] = None,
    collection: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Ingest U.S. statutory / regulatory / public-law text from govinfo.gov.

    Provide EITHER `query` (free-text search across govinfo) OR `collection` (a
    govinfo collection code, e.g. 'USCODE', 'CFR', 'PLAW', 'BILLS'); a collection
    is treated as a filter on the search. Top-N matching packages are fetched and
    ingested. Dedupes by package id / citation.

    Returns {source, query, collection, added, skipped_dupes,
             corpus_size_before, corpus_size_after, ingested, note}.
    """
    limit = max(1, min(int(limit or 5), 25))
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    existing = _existing_source_keys()

    key = _govinfo_key()
    using_demo = key == "DEMO_KEY"

    # Build the search query. govinfo's search service accepts a Lucene-ish query
    # string; we can scope to a collection via `collection:<code>`.
    q_terms: List[str] = []
    if query and query.strip():
        q_terms.append(query.strip())
    if collection and collection.strip():
        q_terms.append(f"collection:{collection.strip().upper()}")
    if not q_terms:
        return {
            "source": "govinfo",
            "query": query or "",
            "collection": collection or "",
            "added": 0,
            "skipped_dupes": 0,
            "corpus_size_before": size_before,
            "corpus_size_after": size_before,
            "ingested": [],
            "note": "Provide a query or a collection code.",
        }
    search_query = " ".join(q_terms)

    cache_key = f"govinfo_search::{search_query}::{limit}"
    packages: List[Dict[str, Any]] = []
    cached = _cache_get(cache_key)

    added = 0
    skipped = 0
    ingested_meta: List[Dict[str, Any]] = []
    new_docs: List[Dict[str, Any]] = []
    note = ""
    if using_demo:
        note = (
            "Using rate-limited DEMO_KEY — set GOVINFO_API_KEY (free at "
            "api.data.gov) for production rate limits."
        )

    with httpx.Client() as client:
        if cached is not None:
            packages = cached
        else:
            body = {
                "query": search_query,
                "pageSize": limit,
                "offsetMark": "*",
                "sorts": [{"field": "relevancy", "sortOrder": "DESC"}],
            }
            resp = _get(client, f"{_GOVINFO_BASE}/search?api_key={key}", kind="POST", json_body=body)
            if resp is None:
                note = (note + " " if note else "") + (
                    "govinfo search returned no data (rate-limited DEMO_KEY or network). "
                    "Set a real GOVINFO_API_KEY to ingest."
                )
            else:
                try:
                    data = resp.json()
                    packages = data.get("results", []) or []
                    _cache_put(cache_key, packages)
                except Exception as exc:
                    print(f"[ingest] govinfo bad JSON: {exc}")

        for pkg in packages[:limit]:
            package_id = pkg.get("packageId") or pkg.get("packageid") or ""
            title = pkg.get("title") or package_id
            coll_code = pkg.get("collectionCode") or (collection or "").upper()
            cite = package_id  # packageId is a stable, unique citation-like id
            key_norm = _norm_key(cite) or _norm_key(title)
            if not package_id:
                continue
            if key_norm and key_norm in existing:
                skipped += 1
                continue
            text = _govinfo_fetch_text(client, package_id)
            if not text.strip():
                skipped += 1
                continue
            existing.add(key_norm)
            url = f"https://www.govinfo.gov/app/details/{package_id}"
            new_docs.append(
                {
                    "id": "gi_" + re.sub(r"[^a-zA-Z0-9]+", "_", package_id)[:60],
                    "source_title": title,
                    "citation": f"{coll_code} · {package_id}",
                    "section": coll_code,
                    "doc_type": "statute",
                    "court": "",
                    "date": pkg.get("dateIssued", "") or pkg.get("lastModified", ""),
                    "url": url,
                    "text": text[:60000],
                }
            )
            ingested_meta.append(
                {
                    "title": title,
                    "package_id": package_id,
                    "collection": coll_code,
                    "url": url,
                }
            )

    if new_docs:
        rag.ingest(new_docs, rag.LEGAL_COLLECTION)
        added = len(new_docs)

    size_after = col.count()
    result = {
        "source": "govinfo",
        "query": query or "",
        "collection": collection or "",
        "added": added,
        "skipped_dupes": skipped,
        "corpus_size_before": size_before,
        "corpus_size_after": size_after,
        "ingested": ingested_meta,
        "note": note.strip(),
    }
    _record_last(result)
    return result


# =============================================================================
# Status
# =============================================================================
def _record_last(result: Dict[str, Any]) -> None:
    global _LAST_INGEST
    _LAST_INGEST = {
        "source": result.get("source", ""),
        "query": result.get("query", ""),
        "added": result.get("added", 0),
        "skipped_dupes": result.get("skipped_dupes", 0),
        "corpus_size_after": result.get("corpus_size_after", 0),
        "at": _now_iso(),
    }


def status() -> Dict[str, Any]:
    """
    Corpus stats for the Data tab: total chunks + a breakdown by source/doc_type
    + the last ingest summary.
    """
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    corpus_size = col.count()

    # Build a sources breakdown from chunk metadata.
    breakdown: Dict[str, int] = {}
    try:
        got = col.get(include=["metadatas"])
        for meta in (got.get("metadatas") or []):
            if not meta:
                continue
            doc_type = meta.get("doc_type", "statute") or "statute"
            cite = (meta.get("citation") or "").lower()
            url = (meta.get("url") or "").lower()
            if doc_type == "opinion" or "courtlistener.com" in url:
                bucket = "courtlistener (case law)"
            elif "federalregister.gov" in url or cite.startswith("fed. reg"):
                bucket = "federal register (rules)"
            elif "ecfr.gov" in url or "cfr §" in cite or "cfr part" in cite or cite.endswith("cfr"):
                bucket = "eCFR (regulations)"
            elif "congress.gov" in url or doc_type == "bill":
                bucket = "congress.gov (legislation)"
            elif "regulations.gov" in url or cite.startswith("regulations.gov"):
                bucket = "regulations.gov (dockets)"
            elif "govinfo.gov" in url or cite.startswith(("uscode", "cfr", "plaw", "bills")):
                bucket = "govinfo (statutes/regs)"
            else:
                bucket = "seed corpus (statutes)"
            breakdown[bucket] = breakdown.get(bucket, 0) + 1
    except Exception as exc:
        print(f"[ingest] status breakdown failed: {exc}")

    return {
        "corpus_size": corpus_size,
        "sources_breakdown": breakdown,
        "last_ingest": _LAST_INGEST,
    }
