"""
Additional Public-Legal-Data connectors (MasterBuildPlan §3.8 / Phase 8) for
L.E.A.D.S. — corpus expansion across the rest of the FEDERAL legal landscape:
regulations, rules, and legislation. Complements ingest.py (CourtListener case
law + govinfo statutes) with four more OFFICIAL government APIs:

  * Federal Register  (federalregister.gov)  — final/proposed rules + notices.
                        KEYLESS official API. Highest value: the actual agency
                        rules implementing FDCPA/FCRA (CFPB, FTC, etc.).
  * eCFR              (ecfr.gov)              — Code of Federal Regulations text.
                        KEYLESS official API (search + versioner).
  * Congress.gov      (api.congress.gov)      — bills + legislative history.
                        Uses the free api.data.gov key (DATA_GOV_API_KEY).
  * Regulations.gov   (api.regulations.gov)   — rulemaking dockets + documents.
                        Uses the same free api.data.gov key.

=============================================================================
GUARDRAILS — THIS FEATURE IS GUARDRAIL-CRITICAL. READ BEFORE EDITING.
=============================================================================
Identical to ingest.py and NON-NEGOTIABLE:
  * OFFICIAL APIs ONLY — documented public endpoints, honest User-Agent, sane
    rate limits/timeouts, robots/ToS respected. No scraping, no bot-protection
    bypass, no CAPTCHA solving, no proxy/IP/rate-limit rotation, no "stealth".
  * On HTTP 429 (or any non-200) we BACK OFF and fall back gracefully — never
    retry-hammer, never try to evade a limit.
  * PUBLIC LEGAL TEXT ONLY — regulations, rules, bills, dockets. We DO NOT
    ingest people-search / PII / personal-data sources.
  * EVERYTHING STAYS LOCAL — fetched text is embedded into the LOCAL ChromaDB
    corpus and raw fetches are cached to backend/.cache/. Nothing is published;
    nothing trains on it.
  * IDEMPOTENT + DEDUPED — keyed by citation/url so re-running never double-
    ingests (shares ingest._existing_source_keys()).
=============================================================================

Each connector returns the SAME shape as ingest.py's connectors:
  {source, query, added, skipped_dupes, corpus_size_before, corpus_size_after,
   ingested, note}
so the Data tab can render them uniformly.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx

from . import ingest, rag

# Reuse ingest.py's vetted helpers so the guardrails live in ONE place.
_get = ingest._get
_clean = ingest._clean
_norm_key = ingest._norm_key
_existing_source_keys = ingest._existing_source_keys
_cache_get = ingest._cache_get
_cache_put = ingest._cache_put
_record_last = ingest._record_last
# (HTTP User-Agent + timeout are applied inside the reused ingest._get helper.)


def _data_gov_key() -> str:
    return (os.getenv("DATA_GOV_API_KEY") or os.getenv("GOVINFO_API_KEY") or "DEMO_KEY").strip()


def _clamp(limit: int, default: int = 5, hi: int = 25) -> int:
    try:
        return max(1, min(int(limit or default), hi))
    except Exception:
        return default


def _empty(source: str, query: str, size_before: int, note: str = "") -> Dict[str, Any]:
    return {
        "source": source,
        "query": query,
        "added": 0,
        "skipped_dupes": 0,
        "corpus_size_before": size_before,
        "corpus_size_after": size_before,
        "ingested": [],
        "note": note,
    }


def _finish(
    source: str,
    query: str,
    col,
    size_before: int,
    new_docs: List[Dict[str, Any]],
    ingested_meta: List[Dict[str, Any]],
    skipped: int,
    note: str = "",
) -> Dict[str, Any]:
    added = 0
    if new_docs:
        rag.ingest(new_docs, rag.LEGAL_COLLECTION)
        added = len(new_docs)
    size_after = col.count()
    result = {
        "source": source,
        "query": query,
        "added": added,
        "skipped_dupes": skipped,
        "corpus_size_before": size_before,
        "corpus_size_after": size_after,
        "ingested": ingested_meta,
        "note": note,
    }
    _record_last(result)
    return result


# =============================================================================
# Federal Register — agency rules & notices (KEYLESS official API)
# =============================================================================
_FR_BASE = "https://www.federalregister.gov/api/v1"


def ingest_federal_register(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Ingest Federal Register documents (final/proposed rules, notices) matching
    `query`. KEYLESS official API. For each hit we prefer the document's plain
    raw text (raw_text_url); otherwise the abstract. doc_type='regulation'.
    """
    limit = _clamp(limit)
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    existing = _existing_source_keys()

    fields = [
        "title", "abstract", "document_number", "html_url", "publication_date",
        "type", "agencies", "raw_text_url", "citation",
    ]
    # Build the query string with httpx.QueryParams so repeated `fields[]` keys
    # and the `conditions[term]` value are encoded correctly (a hand-rolled
    # string previously dropped per_page and over-fetched).
    qp = httpx.QueryParams()
    for f in fields:
        qp = qp.add("fields[]", f)
    qp = qp.add("per_page", str(limit)).add("order", "relevance").add("conditions[term]", query.strip())
    url = f"{_FR_BASE}/documents.json?{qp}"

    skipped = 0
    new_docs: List[Dict[str, Any]] = []
    ingested_meta: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        resp = _get(client, url)
        if resp is None:
            return _empty("federal_register", query, size_before, "Federal Register returned no data (network/rate-limit). Try again.")
        try:
            results = resp.json().get("results", []) or []
        except Exception:
            return _empty("federal_register", query, size_before, "Federal Register returned malformed JSON.")

        for doc in results:
            docnum = (doc.get("document_number") or "").strip()
            title = (doc.get("title") or docnum or "Federal Register document").strip()
            web_url = (doc.get("html_url") or "").strip()
            fr_cite = (doc.get("citation") or "").strip()
            citation = fr_cite or (f"Fed. Reg. No. {docnum}" if docnum else title)
            key = _norm_key(citation) or _norm_key(web_url)
            if not docnum:
                continue
            if key and key in existing:
                skipped += 1
                continue

            # Prefer full plain text; fall back to the abstract.
            text = (doc.get("abstract") or "").strip()
            raw_url = (doc.get("raw_text_url") or "").strip()
            if raw_url:
                raw = _get(client, raw_url)
                if raw is not None and raw.text.strip():
                    full = _clean(raw.text)
                    if len(full) > len(text):
                        text = full
            if not text:
                skipped += 1
                continue
            existing.add(key)

            agencies = ", ".join(
                a.get("name", "") for a in (doc.get("agencies") or []) if isinstance(a, dict) and a.get("name")
            )
            new_docs.append(
                {
                    "id": "fr_" + re.sub(r"[^a-zA-Z0-9]+", "_", docnum)[:60],
                    "source_title": f"{title}" + (f" — {agencies}" if agencies else ""),
                    "citation": citation,
                    "section": (doc.get("type") or "Federal Register"),
                    "doc_type": "regulation",
                    "court": agencies,
                    "date": (doc.get("publication_date") or ""),
                    "url": web_url or f"https://www.federalregister.gov/d/{docnum}",
                    "text": text[:60000],
                }
            )
            ingested_meta.append(
                {"title": title, "citation": citation, "type": doc.get("type", ""),
                 "agencies": agencies, "date": doc.get("publication_date", ""), "url": web_url}
            )

    return _finish("federal_register", query, col, size_before, new_docs, ingested_meta, skipped)


# =============================================================================
# eCFR — Code of Federal Regulations text (KEYLESS official API)
# =============================================================================
_ECFR_BASE = "https://www.ecfr.gov/api"


def _ecfr_title_dates() -> Dict[str, str]:
    """Map CFR title number -> a usable 'up to date as of' date (cached)."""
    cache_key = "ecfr_title_dates"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict) and cached:
        return cached
    out: Dict[str, str] = {}
    with httpx.Client() as client:
        resp = _get(client, f"{_ECFR_BASE}/versioner/v1/titles.json")
        if resp is not None:
            try:
                for t in resp.json().get("titles", []) or []:
                    num = str(t.get("number", "")).strip()
                    date = (t.get("up_to_date_as_of") or t.get("latest_issue_date") or "").strip()
                    if num and date:
                        out[num] = date
            except Exception:
                pass
    if out:
        _cache_put(cache_key, out)
    return out


def _ecfr_section_text(client: httpx.Client, title: str, hierarchy: Dict[str, Any], date: str) -> str:
    """Fetch the node-scoped full text for a CFR hierarchy node (cached)."""
    if not (title and date):
        return ""
    parts = {k: hierarchy.get(k) for k in ("subtitle", "chapter", "subchapter", "part", "subpart", "section")
             if hierarchy.get(k)}
    if not parts:
        return ""
    cache_key = f"ecfr_full::{title}::{date}::{sorted(parts.items())}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return cached.get("text", "")
    qp = httpx.QueryParams(parts)
    resp = _get(client, f"{_ECFR_BASE}/versioner/v1/full/{date}/title-{title}.xml?{qp}")
    text = _clean(resp.text) if (resp is not None and resp.text.strip()) else ""
    if text:
        _cache_put(cache_key, {"text": text})
    return text


def ingest_ecfr(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Ingest Code of Federal Regulations sections matching `query` via the eCFR
    search API, fetching node-scoped full text (versioner) with the search
    excerpt as a graceful fallback. KEYLESS. doc_type='regulation'.
    """
    limit = _clamp(limit)
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    existing = _existing_source_keys()
    title_dates = _ecfr_title_dates()

    skipped = 0
    new_docs: List[Dict[str, Any]] = []
    ingested_meta: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        resp = _get(
            client,
            f"{_ECFR_BASE}/search/v1/results?{httpx.QueryParams({'query': query.strip(), 'per_page': limit})}",
        )
        if resp is None:
            return _empty("ecfr", query, size_before, "eCFR returned no data (network/rate-limit). Try again.")
        try:
            results = resp.json().get("results", []) or []
        except Exception:
            return _empty("ecfr", query, size_before, "eCFR returned malformed JSON.")

        for r in results[:limit]:
            hierarchy = r.get("hierarchy") or {}
            headings = r.get("hierarchy_headings") or {}
            title = str(hierarchy.get("title", "")).strip()
            section = str(hierarchy.get("section", "")).strip()
            part = str(hierarchy.get("part", "")).strip()
            if section:
                citation = f"{title} CFR § {section}"
            elif part:
                citation = f"{title} CFR Part {part}"
            else:
                citation = f"{title} CFR"
            label = (headings.get("section") or headings.get("part") or r.get("headings") or "").strip()
            key = _norm_key(citation)
            if not title:
                continue
            if key and key in existing:
                skipped += 1
                continue

            text = _ecfr_section_text(client, title, hierarchy, title_dates.get(title, ""))
            if not text:
                text = _clean(r.get("full_text_excerpt") or "")
            if not text:
                skipped += 1
                continue
            existing.add(key)

            web_url = f"https://www.ecfr.gov/current/title-{title}" + (f"/section-{section}" if section else "")
            new_docs.append(
                {
                    "id": "ecfr_" + re.sub(r"[^a-zA-Z0-9]+", "_", citation)[:60],
                    "source_title": label or citation,
                    "citation": citation,
                    "section": citation,
                    "doc_type": "regulation",
                    "court": "",
                    "date": title_dates.get(title, ""),
                    "url": web_url,
                    "text": text[:60000],
                }
            )
            ingested_meta.append({"title": label or citation, "citation": citation, "url": web_url})

    return _finish("ecfr", query, col, size_before, new_docs, ingested_meta, skipped)


# =============================================================================
# Congress.gov — bill lookup + legislative history (api.data.gov key)
# =============================================================================
# IMPORTANT: the free Congress.gov v3 API does NOT support free-text keyword
# search on the /bill listing endpoint (a `query` param is silently ignored).
# It DOES robustly support lookup of a SPECIFIC bill by number, so this connector
# ingests a bill (or joint/concurrent/simple resolution) BY REFERENCE — e.g.
# "HR 3221 110", "S 619 118", "118 hjres 7" — pulling its CRS summary as text.
# For topic/keyword discovery use the Federal Register / eCFR / CourtListener
# connectors instead. (Honesty over a connector that returns irrelevant bills.)
_CONGRESS_BASE = "https://api.congress.gov/v3"
_BILL_TYPES = ("hconres", "hjres", "hres", "sconres", "sjres", "sres", "hr", "s")
# Reasonable Congress-number window (93rd ≈ 1973 … 120th) to disambiguate the
# congress number from the bill number when both are present.
_CONGRESS_MIN, _CONGRESS_MAX = 93, 120
_DEFAULT_CONGRESS = 118


def _parse_bill_ref(query: str) -> Optional[Dict[str, Any]]:
    """
    Parse a bill reference like 'HR 3221 110', 'h.r. 3221 (110th)', '118 s 619',
    'hjres7-118' into {congress, type, number}. Returns None if not a bill ref.
    """
    s = (query or "").lower().replace(".", " ").replace("#", " ")
    m_type = re.search(r"\b(hconres|hjres|hres|sconres|sjres|sres|hr|s)\b", s)
    nums = [int(n) for n in re.findall(r"\d+", s)]
    if not m_type or not nums:
        return None
    btype = m_type.group(1)
    if len(nums) >= 2:
        # Whichever number falls in the Congress window is the congress; the other
        # is the bill number. If both could be a congress, take the first as bill #.
        congress = next((n for n in nums if _CONGRESS_MIN <= n <= _CONGRESS_MAX), _DEFAULT_CONGRESS)
        number = next((n for n in nums if n != congress), nums[0])
    else:
        number, congress = nums[0], _DEFAULT_CONGRESS
    return {"congress": congress, "type": btype, "number": number}


def ingest_congress(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Ingest a SPECIFIC Congress.gov bill by reference (e.g. "HR 3221 110"),
    pulling its latest CRS summary as the text (falling back to title + latest
    action). Uses the free api.data.gov key. doc_type='bill'. `limit` is unused
    (a single bill); kept for a uniform connector signature.
    """
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    existing = _existing_source_keys()
    key_param = _data_gov_key()
    note = ""
    if key_param == "DEMO_KEY":
        note = "Using rate-limited DEMO_KEY — set DATA_GOV_API_KEY (free at api.data.gov). "

    ref = _parse_bill_ref(query)
    if not ref:
        return _empty(
            "congress", query, size_before,
            note + "Congress.gov's free API does not support keyword search — enter a "
            "bill BY NUMBER, e.g. 'HR 3221 110' or 'S 619 118'. For topic search use "
            "Federal Register / eCFR / CourtListener.",
        )

    congress, btype, number = ref["congress"], ref["type"], ref["number"]
    type_label = btype.upper().replace("HR", "H.R.")
    citation = f"{type_label} {number} ({congress}th Congress)"
    key = _norm_key(citation)
    if key in existing:
        return _empty("congress", query, size_before, note + f"{citation} is already in the corpus.")

    skipped = 0
    new_docs: List[Dict[str, Any]] = []
    ingested_meta: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        detail = _get(
            client,
            f"{_CONGRESS_BASE}/bill/{congress}/{btype}/{number}?{httpx.QueryParams({'api_key': key_param})}",
        )
        if detail is None:
            return _empty("congress", query, size_before,
                          note + f"{citation} not found (check the bill number and Congress).")
        try:
            bill = detail.json().get("bill", {}) or {}
        except Exception:
            return _empty("congress", query, size_before, note + "Congress.gov returned malformed JSON.")
        if not bill:
            return _empty("congress", query, size_before, note + f"{citation} not found.")

        title = (bill.get("title") or citation).strip()
        latest = bill.get("latestAction") or {}

        # Pull the latest CRS summary text for real legislative substance.
        text = ""
        s_resp = _get(
            client,
            f"{_CONGRESS_BASE}/bill/{congress}/{btype}/{number}/summaries?{httpx.QueryParams({'api_key': key_param})}",
        )
        if s_resp is not None:
            try:
                summaries = s_resp.json().get("summaries", []) or []
                if summaries:
                    text = _clean(summaries[-1].get("text") or "")
            except Exception:
                pass
        if not text:
            action = f"Latest action ({latest.get('actionDate','')}): {latest.get('text','')}".strip()
            text = f"{title}. {action}".strip(". ")
        if not text:
            return _empty("congress", query, size_before, note + f"{citation} has no summary text available yet.")
        existing.add(key)

        chamber = "house-bill" if btype in ("hr", "hjres", "hconres", "hres") else "senate-bill"
        web_url = f"https://www.congress.gov/bill/{congress}th-congress/{chamber}/{number}"
        new_docs.append(
            {
                "id": "cong_" + re.sub(r"[^a-zA-Z0-9]+", "_", citation)[:60],
                "source_title": title,
                "citation": citation,
                "section": f"{congress}th Congress",
                "doc_type": "bill",
                "court": "",
                "date": (latest.get("actionDate") or bill.get("updateDate") or ""),
                "url": web_url,
                "text": text[:60000],
            }
        )
        ingested_meta.append({"title": title, "citation": citation, "url": web_url})

    return _finish("congress", query, col, size_before, new_docs, ingested_meta, skipped, note=note.strip())


# =============================================================================
# Regulations.gov — rulemaking dockets & documents (api.data.gov key)
# =============================================================================
_REGS_BASE = "https://api.regulations.gov/v4"


def ingest_regulations(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Ingest Regulations.gov documents (proposed/final rules, notices, supporting
    docs) matching `query`. Uses the free api.data.gov key. Page size is clamped
    to the API's minimum of 5. doc_type='regulation'.
    """
    limit = max(5, _clamp(limit, default=5))  # Regulations.gov requires page[size] >= 5
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    existing = _existing_source_keys()
    key_param = _data_gov_key()
    note = ""
    if key_param == "DEMO_KEY":
        note = "Using rate-limited DEMO_KEY — set DATA_GOV_API_KEY (free at api.data.gov)."

    skipped = 0
    new_docs: List[Dict[str, Any]] = []
    ingested_meta: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        params = httpx.QueryParams(
            {"filter[searchTerm]": query.strip(), "page[size]": limit,
             "sort": "-postedDate", "api_key": key_param}
        )
        resp = _get(client, f"{_REGS_BASE}/documents?{params}")
        if resp is None:
            return _empty("regulations", query, size_before, (note + " " if note else "") + "Regulations.gov returned no data.")
        try:
            data = resp.json().get("data", []) or []
        except Exception:
            return _empty("regulations", query, size_before, "Regulations.gov returned malformed JSON.")

        for d in data:
            doc_id = (d.get("id") or "").strip()
            attrs = d.get("attributes") or {}
            title = (attrs.get("title") or doc_id or "Regulations.gov document").strip()
            citation = f"Regulations.gov {doc_id}"
            key = _norm_key(citation)
            if not doc_id:
                continue
            if key and key in existing:
                skipped += 1
                continue

            highlighted = _clean(attrs.get("highlightedContent") or "")
            doc_type_label = attrs.get("documentType", "")
            agency = attrs.get("agencyId", "")
            text = ". ".join(
                p for p in [title, f"Type: {doc_type_label}" if doc_type_label else "",
                            f"Agency: {agency}" if agency else "", highlighted] if p
            ).strip()
            if len(text) < 20:  # not enough substance to be useful
                skipped += 1
                continue
            existing.add(key)

            web_url = f"https://www.regulations.gov/document/{doc_id}"
            new_docs.append(
                {
                    "id": "regs_" + re.sub(r"[^a-zA-Z0-9]+", "_", doc_id)[:60],
                    "source_title": title,
                    "citation": citation,
                    "section": doc_type_label or "Regulations.gov",
                    "doc_type": "regulation",
                    "court": agency,
                    "date": (attrs.get("postedDate") or ""),
                    "url": web_url,
                    "text": text[:40000],
                }
            )
            ingested_meta.append(
                {"title": title, "citation": citation, "type": doc_type_label, "agency": agency, "url": web_url}
            )

    return _finish("regulations", query, col, size_before, new_docs, ingested_meta, skipped, note=note)
