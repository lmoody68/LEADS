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


# =============================================================================
# OpenStates — STATE legislation full-text search (free OPENSTATES_API_KEY)
# =============================================================================
# Unlike Congress.gov's free API, OpenStates v3 DOES support keyword search of
# state bills (`/bills?q=`), filling the state-legislation gap. Free key (10
# req/min, 250/day) from https://openstates.org/accounts/signup/ — set it as
# OPENSTATES_API_KEY in backend/.env. The key is sent via the X-API-KEY HEADER
# (kept out of the URL/logs).
_OPENSTATES_BASE = "https://v3.openstates.org"


def ingest_openstates(query: str, jurisdiction: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
    """
    Ingest STATE bills matching `query` from OpenStates v3 (optionally scoped to a
    `jurisdiction` like 'California' or 'ca'). Uses each bill's abstract as text
    (falling back to title + latest action). doc_type='bill'. Requires a free
    OPENSTATES_API_KEY; returns a clear note (added=0) when it is unset.
    """
    limit = _clamp(limit)
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    key = (os.getenv("OPENSTATES_API_KEY") or "").strip()
    if not key:
        return _empty(
            "openstates", query, size_before,
            "No OPENSTATES_API_KEY configured — get a free key at "
            "https://openstates.org/accounts/signup/ and set OPENSTATES_API_KEY in backend/.env.",
        )

    existing = _existing_source_keys()
    qp = httpx.QueryParams({"q": query.strip(), "per_page": limit, "sort": "latest_action_desc"})
    qp = qp.add("include", "abstracts")
    if jurisdiction and jurisdiction.strip():
        qp = qp.add("jurisdiction", jurisdiction.strip())

    skipped = 0
    new_docs: List[Dict[str, Any]] = []
    ingested_meta: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        resp = _get(client, f"{_OPENSTATES_BASE}/bills?{qp}", extra_headers={"X-API-KEY": key})
        if resp is None:
            return _empty("openstates", query, size_before,
                          "OpenStates returned no data (rate-limit/network) — try again shortly.")
        try:
            results = resp.json().get("results", []) or []
        except Exception:
            return _empty("openstates", query, size_before, "OpenStates returned malformed JSON.")

        for b in results[:limit]:
            identifier = (b.get("identifier") or "").strip()
            jur = (b.get("jurisdiction") or {}).get("name", "") if isinstance(b.get("jurisdiction"), dict) else ""
            session = (b.get("session") or "").strip()
            title = (b.get("title") or identifier or "State bill").strip()
            web_url = (b.get("openstates_url") or "").strip()
            citation = f"{jur} {identifier} ({session})".strip()
            key_norm = _norm_key(citation) or _norm_key(web_url)
            if not identifier:
                continue
            if key_norm and key_norm in existing:
                skipped += 1
                continue

            abstracts = [a.get("abstract", "") for a in (b.get("abstracts") or []) if isinstance(a, dict)]
            text = _clean(" ".join(x for x in abstracts if x))
            if not text:
                text = f"{title}. Latest action: {b.get('latest_action_description','')}".strip(". ")
            if not text:
                skipped += 1
                continue
            existing.add(key_norm)

            new_docs.append(
                {
                    "id": "os_" + re.sub(r"[^a-zA-Z0-9]+", "_", citation)[:60],
                    "source_title": title,
                    "citation": citation,
                    "section": jur or "State legislature",
                    "doc_type": "bill",
                    "court": jur,
                    "date": (b.get("latest_action_date") or ""),
                    "url": web_url,
                    "text": text[:60000],
                }
            )
            ingested_meta.append({"title": title, "citation": citation, "url": web_url})

    return _finish("openstates", query, col, size_before, new_docs, ingested_meta, skipped)


# =============================================================================
# RECAP / PACER dockets — federal court records via CourtListener (token)
# =============================================================================
# CourtListener's RECAP archive mirrors PACER federal court dockets (filings,
# parties, docket entries) and is searchable full-text via the v4 search API
# with type=r. PUBLIC court records via the OFFICIAL API — for LEGAL RESEARCH
# (litigation, not person-location). The COURTLISTENER_API_TOKEN raises rate
# limits; anonymous works but is throttled.
_CL_BASE = "https://www.courtlistener.com"


def ingest_recap(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Ingest federal court DOCKETS matching `query` from CourtListener's RECAP
    archive (search type=r). Text = case metadata (cause, nature of suit, court,
    docket number, assigned judge) + the filed-document descriptions/snippets.
    doc_type='docket'. Dedupes by docket id / citation. Graceful on any failure.
    """
    limit = _clamp(limit)
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    existing = _existing_source_keys()

    token = (os.getenv("COURTLISTENER_API_TOKEN") or "").strip()
    headers = {"Authorization": f"Token {token}"} if token else None
    note = "" if token else "No COURTLISTENER_API_TOKEN — RECAP search is heavily rate-limited anonymously."

    qp = httpx.QueryParams({"type": "r", "q": query.strip(), "order_by": "dateFiled desc"})

    skipped = 0
    new_docs: List[Dict[str, Any]] = []
    ingested_meta: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        resp = _get(client, f"{_CL_BASE}/api/rest/v4/search/?{qp}", extra_headers=headers)
        if resp is None:
            return _empty("recap", query, size_before, (note + " " if note else "") + "RECAP search returned no data.")
        try:
            results = resp.json().get("results", []) or []
        except Exception:
            return _empty("recap", query, size_before, "RECAP returned malformed JSON.")

        for d in results[:limit]:
            docket_id = d.get("docket_id")
            case_name = (d.get("caseName") or "Federal docket").strip()
            docket_no = (d.get("docketNumber") or "").strip()
            court = (d.get("court") or d.get("court_citation_string") or "").strip()
            cite_court = (d.get("court_citation_string") or d.get("court_id") or court).strip()
            citation = f"{docket_no} ({cite_court})".strip() if docket_no else f"{case_name} ({cite_court})"
            abs_url = (d.get("docket_absolute_url") or "").strip()
            web_url = (_CL_BASE + abs_url) if abs_url.startswith("/") else abs_url
            key = (f"docket:{docket_id}" if docket_id else "") or _norm_key(citation) or _norm_key(web_url)
            if key and key in existing:
                skipped += 1
                continue

            # Build legal-research text from the docket's metadata + filings.
            meta_lines = [
                f"Case: {case_name}",
                f"Court: {court}" if court else "",
                f"Docket No.: {docket_no}" if docket_no else "",
                f"Date filed: {d.get('dateFiled','')}" if d.get("dateFiled") else "",
                f"Cause: {d.get('cause','')}" if d.get("cause") else "",
                f"Nature of suit: {d.get('suitNature','')}" if d.get("suitNature") else "",
                f"Assigned to: {d.get('assignedTo','')}" if d.get("assignedTo") else "",
            ]
            doc_bits: List[str] = []
            for rd in (d.get("recap_documents") or [])[:5]:
                if not isinstance(rd, dict):
                    continue
                desc = (rd.get("description") or "").strip()
                snip = _clean(rd.get("snippet") or "")
                bit = " — ".join(p for p in [desc, snip] if p)
                if bit:
                    doc_bits.append(f"• {bit}")
            text = "\n".join(p for p in meta_lines if p)
            if doc_bits:
                text += "\n\nFilings:\n" + "\n".join(doc_bits)
            if len(text.strip()) < 25:
                skipped += 1
                continue
            existing.add(key)

            new_docs.append(
                {
                    "id": "recap_" + re.sub(r"[^a-zA-Z0-9]+", "_", str(docket_id or citation))[:60],
                    "source_title": case_name,
                    "citation": citation,
                    "section": court or "Federal docket",
                    "doc_type": "docket",
                    "court": court,
                    "date": (d.get("dateFiled") or ""),
                    "url": web_url,
                    "text": text[:60000],
                }
            )
            ingested_meta.append({"title": case_name, "citation": citation, "court": court, "url": web_url})

    return _finish("recap", query, col, size_before, new_docs, ingested_meta, skipped, note=note)


# =============================================================================
# Oyez — Supreme Court case summaries (KEYLESS, oyez.org)
# =============================================================================
# Oyez provides plain-language SCOTUS summaries (facts / question / conclusion) —
# excellent for the layman's-terms transcriber + tutor. NOTE: the Oyez API does
# NOT support full-text keyword search, so this ingests a SCOTUS TERM by YEAR
# (e.g. "2019"); a non-year input returns an honest note. doc_type='opinion'.
_OYEZ_BASE = "https://api.oyez.org"


def ingest_oyez(query: str, limit: int = 5) -> Dict[str, Any]:
    limit = _clamp(limit)
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()

    year = (query or "").strip()
    if not re.fullmatch(r"(19|20)\d{2}", year):
        return _empty(
            "oyez", query, size_before,
            "Oyez's API has no keyword search — enter a SCOTUS TERM YEAR (e.g. 2019) to "
            "ingest that term's cases. For topic search use CourtListener.",
        )

    existing = _existing_source_keys()
    skipped = 0
    new_docs: List[Dict[str, Any]] = []
    ingested_meta: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        resp = _get(client, f"{_OYEZ_BASE}/cases?{httpx.QueryParams({'filter': f'term:{year}', 'per_page': limit})}")
        if resp is None:
            return _empty("oyez", query, size_before, "Oyez returned no data (network/rate-limit).")
        try:
            cases = resp.json()
        except Exception:
            return _empty("oyez", query, size_before, "Oyez returned malformed JSON.")
        if not isinstance(cases, list):
            cases = []

        for case in cases[:limit]:
            href = (case.get("href") or "").strip()
            name = (case.get("name") or "SCOTUS case").strip()
            cite = case.get("citation") or {}
            if isinstance(cite, dict) and cite.get("volume"):
                page = cite.get("page") or "___"  # some cases have a volume but no page yet
                citation = f"{cite.get('volume')} U.S. {page} ({cite.get('year', year)})"
            else:
                citation = f"{name} ({year})"
            key = _norm_key(citation) or _norm_key(href)
            if key and key in existing:
                skipped += 1
                continue

            # Fetch the detail for facts / question / conclusion.
            facts = question = conclusion = ""
            if href:
                d = _get(client, href)
                if d is not None:
                    try:
                        det = d.json()
                        facts = _clean(_oyez_text(det.get("facts_of_the_case")))
                        question = _clean(_oyez_text(det.get("question")))
                        conclusion = _clean(_oyez_text(det.get("conclusion")))
                    except Exception:
                        pass
            description = _clean(_oyez_text(case.get("description")))
            parts = [f"{name}.", description]
            if facts:
                parts.append(f"Facts: {facts}")
            if question:
                parts.append(f"Question: {question}")
            if conclusion:
                parts.append(f"Conclusion: {conclusion}")
            text = "\n\n".join(p for p in parts if p and p.strip())
            if len(text.strip()) < 30:
                skipped += 1
                continue
            existing.add(key)

            web_url = (case.get("justia_url") or "").strip() or href
            new_docs.append(
                {
                    "id": "oyez_" + re.sub(r"[^a-zA-Z0-9]+", "_", citation)[:60],
                    "source_title": name,
                    "citation": citation,
                    "section": "Supreme Court of the United States",
                    "doc_type": "opinion",
                    "court": "Supreme Court of the United States",
                    "date": str((cite.get("year") if isinstance(cite, dict) else "") or year),
                    "url": web_url,
                    "text": text[:60000],
                }
            )
            ingested_meta.append({"title": name, "citation": citation, "url": web_url})

    return _finish("oyez", query, col, size_before, new_docs, ingested_meta, skipped)


def _oyez_text(val: Any) -> str:
    """Oyez fields can be a string or a {'plain_text'|'html'} dict."""
    if isinstance(val, dict):
        return val.get("plain_text") or val.get("html") or ""
    return val if isinstance(val, str) else ""


# =============================================================================
# FBI Crime Data Explorer — AGGREGATE crime statistics (api.data.gov key)
# =============================================================================
# CDE serves AGGREGATE, published crime/arrest statistics — never individual
# records. Ingested as a readable text summary for criminal-justice CONTEXT in
# the research/education workflow. doc_type='statistic'. This is NOT case law or
# a person-lookup; it is national-level numbers only.
_CDE_BASE = "https://api.usa.gov/crime/fbi/cde"
_CDE_DEFAULT_FROM = "01-2019"
_CDE_DEFAULT_TO = "12-2022"


def ingest_fbi_cde(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Ingest a text SUMMARY of FBI CDE national ARREST statistics. query = an
    offense ID ('all' is always available; other IDs per cde.ucr.cjis.gov) with
    an optional 'YYYY-YYYY' range. Falls back to ALL-offenses national totals if
    the requested offense isn't served. `limit` unused. AGGREGATE numbers only.
    """
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()
    key = _data_gov_key()

    # Parse an optional YYYY-YYYY range; offense = the remaining words, slugified.
    yrs = re.findall(r"(19|20)\d{2}", query or "")
    rng = re.search(r"((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})", query or "")
    if rng:
        frm, to = f"01-{rng.group(1)}", f"12-{rng.group(2)}"
        offense_raw = re.sub(r"((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})", "", query).strip()
    else:
        frm, to = _CDE_DEFAULT_FROM, _CDE_DEFAULT_TO
        offense_raw = re.sub(r"\b(19|20)\d{2}\b", "", query or "").strip()
    offense = re.sub(r"\s+", "_", offense_raw.lower()) or "all"

    def _fetch(client: httpx.Client, off: str) -> Optional[Dict[str, Any]]:
        url = f"{_CDE_BASE}/arrest/national/{off}?{httpx.QueryParams({'from': frm, 'to': to, 'type': 'counts', 'API_KEY': key})}"
        resp = _get(client, url)
        if resp is None:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        return data if (data.get("rates") or data.get("actuals")) else None

    note = ""
    with httpx.Client() as client:
        data = _fetch(client, offense)
        # The national arrest endpoint only serves a documented set of offense IDs;
        # if the requested one isn't available, fall back to ALL-offenses national
        # totals (honest note) rather than failing.
        if data is None and offense != "all":
            data = _fetch(client, "all")
            if data is not None:
                note = (f"Offense '{offense}' isn't available at the national arrest level "
                        "(see cde.ucr.cjis.gov for valid offense IDs); showing ALL-offenses national totals.")
                offense = "all"
        if data is None:
            return _empty("fbi_cde", query, size_before,
                          f"FBI CDE returned no data for '{offense}' ({frm}–{to}). Try offense 'all' "
                          "or a different year range.")

        citation = f"FBI CDE national arrests · {offense} · {frm}–{to}"
        existing = _existing_source_keys()
        if _norm_key(citation) in existing:
            return _empty("fbi_cde", query, size_before, f"{citation} already in the corpus.")

        text = _summarize_cde(offense, frm, to, data)
        if not text:
            return _empty("fbi_cde", query, size_before, f"No usable CDE series for '{offense}'.")

        web_url = "https://cde.ucr.cjis.gov/"
        new_docs = [{
            "id": "cde_" + re.sub(r"[^a-zA-Z0-9]+", "_", f"{offense}_{frm}_{to}")[:60],
            "source_title": f"FBI CDE — national arrests: {offense} ({frm}–{to})",
            "citation": citation,
            "section": "FBI Crime Data Explorer (aggregate statistics)",
            "doc_type": "statistic",
            "court": "",
            "date": to,
            "url": web_url,
            "text": text,
        }]
        ingested_meta = [{"title": new_docs[0]["source_title"], "citation": citation, "url": web_url}]

    return _finish("fbi_cde", query, col, size_before, new_docs, ingested_meta, 0, note=note)


def _summarize_cde(offense: str, frm: str, to: str, data: Dict[str, Any]) -> str:
    """Turn the CDE rates/actuals time series into a concise per-year text summary."""
    lines = [
        f"FBI Crime Data Explorer — national ARREST statistics for offense '{offense}', {frm} to {to}.",
        "AGGREGATE, published national numbers only — NOT individual records, NOT case law.",
    ]

    def _by_year(series: Dict[str, Any]) -> Dict[str, list]:
        years: Dict[str, list] = {}
        for period, val in (series or {}).items():
            m = re.match(r"\d{2}-((?:19|20)\d{2})", str(period))
            if m and isinstance(val, (int, float)):
                years.setdefault(m.group(1), []).append(float(val))
        return years

    rates = data.get("rates") or {}
    actuals = data.get("actuals") or {}
    for label, series in list(rates.items())[:1]:  # the primary "United States Arrests" rate series
        yb = _by_year(series)
        if yb:
            lines.append(f"\nArrest rate per 100,000 ({label}), yearly average:")
            for yr in sorted(yb):
                vals = yb[yr]
                lines.append(f"  {yr}: {round(sum(vals)/len(vals), 1)} (avg over {len(vals)} months)")
    for label, series in list(actuals.items())[:1]:
        yb = _by_year(series)
        if yb:
            lines.append(f"\nEstimated arrest counts ({label}), yearly total:")
            for yr in sorted(yb):
                lines.append(f"  {yr}: {int(sum(yb[yr])):,}")
    lines.append("\nSource: FBI Crime Data Explorer (cde.ucr.cjis.gov), via api.usa.gov.")
    return "\n".join(lines) if len(lines) > 3 else ""
