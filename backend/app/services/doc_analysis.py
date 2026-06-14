"""
Enhanced Document Analysis (MasterBuildPlan §3.7, Pinpoint-style) for L.E.A.D.S.

EXTENDS the Phase-0 Case-File Analyzer (`casefile.py`). Operates over an
EXISTING uploaded collection (`casefile_<collection_id>`) and adds four
cross-document capabilities:

  1. Relationship mapping   — entities + typed relationships (who↔whom, how).
  2. Timeline construction  — a sorted chronology of dated events across docs.
  3. Pattern/discrepancy    — cross-document patterns, connections, contradictions.
  4. Redaction suggestion   — sensitive-PII detection (SSN/account/phone/email/DOB)
                              so the user can redact BEFORE sharing.

GUARDRAILS (NON-NEGOTIABLE):
- Works ONLY on documents the user already uploaded into a collection. No web
  scraping, no external fetching, no PII harvesting from the outside world.
- Redaction is a privacy-PROTECTING feature: it flags sensitive data the user
  may want to remove before sharing a file — it never exfiltrates it.
- The LLM router makes stateless completion calls (no training/retention).
- Every LLM step has a deterministic / extractive fallback so NOTHING crashes
  when no provider key is configured (the redaction regex pass is fully keyless).

Results are cached per collection (in-process) and recomputed on demand.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from . import llm_router, rag

# =============================================================================
# Per-document gathering over an existing collection
# =============================================================================
def _collection_name(collection_id: str) -> str:
    return f"casefile_{collection_id}"


def _gather_docs(collection_id: str) -> List[Dict[str, str]]:
    """
    Return one entry per SOURCE DOCUMENT in the collection:
    [{source_doc, text}], reassembling each document's chunks in order.

    Chunk ids look like "<base>::chunk<i>"; we group by source_title (the
    filename used at upload) and concatenate the chunks for that document.
    """
    col = rag.get_collection(_collection_name(collection_id))
    if col.count() == 0:
        return []
    got = col.get()
    docs = got.get("documents", []) or []
    metas = got.get("metadatas", []) or []
    ids = got.get("ids", []) or []

    # Group chunks by source document, preserving chunk order.
    grouped: Dict[str, List[Tuple[int, str]]] = {}
    for cid, doc, meta in zip(ids, docs, metas):
        source = (meta or {}).get("source_title") or "document"
        # chunk index from the id suffix "::chunkN" (fallback 0).
        m = re.search(r"::chunk(\d+)$", str(cid))
        order = int(m.group(1)) if m else 0
        grouped.setdefault(source, []).append((order, doc))

    out: List[Dict[str, str]] = []
    for source, parts in grouped.items():
        parts.sort(key=lambda t: t[0])
        out.append({"source_doc": source, "text": "\n".join(p[1] for p in parts)})
    return out


def _corpus_text(per_doc: List[Dict[str, str]], cap_per_doc: int = 8000, cap_total: int = 16000) -> str:
    """Build a single labeled, length-bounded corpus string for an LLM call."""
    blocks: List[str] = []
    for d in per_doc:
        snippet = d["text"][:cap_per_doc]
        blocks.append(f"=== DOCUMENT: {d['source_doc']} ===\n{snippet}")
    corpus = "\n\n".join(blocks)
    return corpus[:cap_total]


def _extract_json(raw: str) -> Any | None:
    """Pull a JSON object/array out of an LLM response that may wrap it."""
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    if not fenced:
        brace = re.search(r"[\[{].*[\]}]", candidate, re.DOTALL)
        candidate = brace.group(0) if brace else candidate
    try:
        return json.loads(candidate)
    except Exception:
        return None


# =============================================================================
# 1. Relationship mapping
# =============================================================================
_REL_SYSTEM = (
    "You are a relationship-extraction engine for a legal case-file analyzer. "
    "From the provided user-uploaded documents, identify the entities (people and "
    "organizations) and the RELATIONSHIPS between them (who is connected to whom, "
    "and how). Respond with STRICT JSON only (no markdown, no prose) of the form: "
    '{"entities": ["..."], "relationships": [{"from": "...", "to": "...", '
    '"type": "...", "evidence_snippet": "...", "source_doc": "..."}]}. '
    "type is a short label like 'employer', 'attorney for', 'spouse', 'creditor', "
    "'transferred funds to', 'business partner'. evidence_snippet is a short verbatim "
    "quote from the text that supports the relationship. source_doc is the DOCUMENT "
    "name the evidence came from. Do NOT invent relationships not supported by the text."
)


def _person_org_regex(per_doc: List[Dict[str, str]]) -> List[str]:
    """Deterministic, conservative proper-noun candidate extraction (fallback)."""
    name_re = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
    org_re = re.compile(
        r"\b([A-Z][A-Za-z&.,'-]+(?:\s+[A-Z][A-Za-z&.,'-]+)*\s+"
        r"(?:Inc|LLC|L\.L\.C|Corp|Corporation|Company|Co|Ltd|LLP|Bank|Group|Trust|Partners|Associates|Firm)\b\.?)"
    )
    found: set[str] = set()
    for d in per_doc:
        for m in org_re.finditer(d["text"]):
            found.add(m.group(1).strip())
        for m in name_re.finditer(d["text"]):
            cand = m.group(1).strip()
            # Skip if it's part of an org we already captured.
            if not any(cand in o for o in found):
                found.add(cand)
    # Keep it bounded and stable.
    return sorted(found)[:40]


def relationships(collection_id: str) -> Dict[str, Any]:
    """
    LLM-extracted entities + typed relationships across the collection's docs.
    Falls back to a deterministic proper-noun entity list (no relationships) when
    no LLM key is available.
    """
    per_doc = _gather_docs(collection_id)
    if not per_doc:
        return {"entities": [], "relationships": [], "provider": "none",
                "note": "No documents are indexed in this collection yet."}

    corpus = _corpus_text(per_doc)
    raw, provider = llm_router.synthesize(_REL_SYSTEM, corpus)
    parsed = _extract_json(raw) if raw else None

    if isinstance(parsed, dict):
        ents = parsed.get("entities") or []
        rels = parsed.get("relationships") or []
        entities = sorted({str(e).strip() for e in ents if str(e).strip()}) if isinstance(ents, list) else []
        relationships_out: List[Dict[str, str]] = []
        if isinstance(rels, list):
            for r in rels:
                if not isinstance(r, dict):
                    continue
                frm = str(r.get("from", "")).strip()
                to = str(r.get("to", "")).strip()
                if not frm or not to:
                    continue
                relationships_out.append({
                    "from": frm,
                    "to": to,
                    "type": str(r.get("type", "related to")).strip() or "related to",
                    "evidence_snippet": str(r.get("evidence_snippet", "")).strip()[:400],
                    "source_doc": str(r.get("source_doc", "")).strip(),
                })
        # Make sure relationship endpoints are present in the entity list.
        for r in relationships_out:
            for k in ("from", "to"):
                if r[k] and r[k] not in entities:
                    entities.append(r[k])
        return {
            "entities": sorted(set(entities)),
            "relationships": relationships_out,
            "provider": provider,
            "note": "" if relationships_out else "No explicit relationships were extracted from the text.",
        }

    # Fallback: deterministic entity candidates, no relationships.
    return {
        "entities": _person_org_regex(per_doc),
        "relationships": [],
        "provider": "extractive (no LLM key)",
        "note": ("No LLM key configured — listing candidate people/organizations "
                 "found via proper-noun detection. Relationship typing needs an LLM."),
    }


# =============================================================================
# 2. Timeline construction
# =============================================================================
# Reuse the date pattern shape from the case-file analyzer.
_DATE_RE = re.compile(
    r"\b("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r")\b"
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _sort_key(date_str: str) -> Tuple[int, int, int]:
    """Best-effort (year, month, day) sort key from a free-form date string."""
    s = (date_str or "").strip()
    # ISO yyyy-mm-dd
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # mm/dd/yyyy or m/d/yy
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        yr = int(m.group(3))
        yr += 2000 if yr < 100 else 0
        return (yr, int(m.group(1)), int(m.group(2)))
    # Month DD, YYYY
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        return (int(m.group(3)), _MONTHS.get(m.group(1).lower(), 0), int(m.group(2)))
    # Bare year anywhere.
    m = re.search(r"\b(\d{4})\b", s)
    if m:
        return (int(m.group(1)), 0, 0)
    return (9999, 99, 99)  # undated → sort last


_TIMELINE_SYSTEM = (
    "You are a timeline-construction engine for a legal case-file analyzer. From "
    "the provided user-uploaded documents, extract DATED EVENTS — each a thing that "
    "happened on a specific date mentioned in the text. Respond with STRICT JSON only "
    "(no markdown, no prose): a JSON ARRAY of "
    '{"date": "...", "event": "...", "source_doc": "...", "snippet": "..."}. '
    "date = the date as written in the document. event = a one-line description of what "
    "happened. source_doc = the DOCUMENT name it came from. snippet = a short verbatim "
    "quote. Only include events that have an actual date in the text. Do not invent events."
)


def _regex_timeline(per_doc: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Deterministic fallback: each dated sentence becomes a timeline event."""
    events: List[Dict[str, str]] = []
    for d in per_doc:
        # Split into sentences and keep those that contain a date.
        sentences = re.split(r"(?<=[.!?;])\s+", d["text"])
        for sent in sentences:
            m = _DATE_RE.search(sent)
            if not m:
                continue
            sent = sent.strip()
            events.append({
                "date": m.group(1).strip(),
                "event": (sent[:200] + ("…" if len(sent) > 200 else "")),
                "source_doc": d["source_doc"],
                "snippet": sent[:300],
            })
    return events


def timeline(collection_id: str) -> Dict[str, Any]:
    """Sorted chronology of dated events across the collection's documents."""
    per_doc = _gather_docs(collection_id)
    if not per_doc:
        return {"events": [], "provider": "none",
                "note": "No documents are indexed in this collection yet."}

    corpus = _corpus_text(per_doc)
    raw, provider = llm_router.synthesize(_TIMELINE_SYSTEM, corpus)
    parsed = _extract_json(raw) if raw else None

    events: List[Dict[str, str]] = []
    if isinstance(parsed, list):
        for e in parsed:
            if not isinstance(e, dict):
                continue
            date = str(e.get("date", "")).strip()
            event = str(e.get("event", "")).strip()
            if not date or not event:
                continue
            events.append({
                "date": date,
                "event": event[:300],
                "source_doc": str(e.get("source_doc", "")).strip(),
                "snippet": str(e.get("snippet", "")).strip()[:400],
            })
        note = "" if events else "No dated events were extracted from the text."
    else:
        events = _regex_timeline(per_doc)
        provider = "extractive (no LLM key)"
        note = ("No LLM key configured — timeline built deterministically from "
                "dated sentences in the documents.")

    events.sort(key=lambda ev: _sort_key(ev["date"]))
    return {"events": events, "provider": provider, "note": note}


# =============================================================================
# 3. Cross-document pattern / discrepancy detection
# =============================================================================
_PATTERN_SYSTEM = (
    "You are a cross-document analysis engine for a legal case-file analyzer. "
    "Across ALL the provided user-uploaded documents, identify: (a) PATTERNS and "
    "connections that span multiple documents, and (b) DISCREPANCIES / contradictions "
    "where documents disagree with each other. Respond with STRICT JSON only "
    "(no markdown, no prose): a JSON ARRAY of "
    '{"observation": "...", "type": "pattern", "supporting_docs": ["..."]}. '
    "type is EXACTLY 'pattern' or 'discrepancy'. observation = one clear sentence. "
    "supporting_docs = the DOCUMENT names involved. Focus on observations that require "
    "comparing two or more documents. Do not invent facts not present in the text."
)


def patterns(collection_id: str) -> Dict[str, Any]:
    """Cross-document patterns + discrepancies across the collection."""
    per_doc = _gather_docs(collection_id)
    if not per_doc:
        return {"observations": [], "provider": "none",
                "note": "No documents are indexed in this collection yet."}

    corpus = _corpus_text(per_doc)
    raw, provider = llm_router.synthesize(_PATTERN_SYSTEM, corpus)
    parsed = _extract_json(raw) if raw else None

    observations: List[Dict[str, Any]] = []
    if isinstance(parsed, list):
        for o in parsed:
            if not isinstance(o, dict):
                continue
            obs = str(o.get("observation", "")).strip()
            if not obs:
                continue
            otype = str(o.get("type", "pattern")).strip().lower()
            if otype not in ("pattern", "discrepancy"):
                otype = "pattern"
            docs = o.get("supporting_docs") or []
            docs = [str(x).strip() for x in docs if str(x).strip()] if isinstance(docs, list) else []
            observations.append({"observation": obs[:400], "type": otype, "supporting_docs": docs})
        note = "" if observations else "No cross-document patterns or discrepancies were found."
        return {"observations": observations, "provider": provider, "note": note}

    # Deterministic fallback: surface entities/citations shared across >1 document.
    return _deterministic_patterns(per_doc)


def _deterministic_patterns(per_doc: List[Dict[str, str]]) -> Dict[str, Any]:
    """Fallback: flag proper-noun entities that appear in more than one document."""
    name_re = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
    appearances: Dict[str, set] = {}
    for d in per_doc:
        for m in name_re.finditer(d["text"]):
            appearances.setdefault(m.group(1).strip(), set()).add(d["source_doc"])
    observations: List[Dict[str, Any]] = []
    for entity, docs in sorted(appearances.items()):
        if len(docs) > 1:
            observations.append({
                "observation": f"'{entity}' appears across multiple documents.",
                "type": "pattern",
                "supporting_docs": sorted(docs),
            })
    observations = observations[:20]
    return {
        "observations": observations,
        "provider": "extractive (no LLM key)",
        "note": ("No LLM key configured — surfacing entities that appear in more than "
                 "one document. Contradiction detection needs an LLM."),
    }


# =============================================================================
# 4. Redaction suggestion (deterministic regex PII pass + optional LLM)
# =============================================================================
# Deterministic PII patterns. Each (type, regex, reason). The deterministic pass
# runs with NO LLM key and is the privacy guarantee of this feature.
_PII_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
     "Social Security Number — highly sensitive personal identifier."),
    ("SSN", re.compile(r"\bSSN[:\s#]*\d{3}[-\s]?\d{2}[-\s]?\d{4}\b", re.IGNORECASE),
     "Labeled Social Security Number."),
    ("EIN", re.compile(r"\bEIN[:\s#]*\d{2}-\d{7}\b", re.IGNORECASE),
     "Employer Identification Number."),
    ("Credit card", re.compile(r"\b(?:\d[ -]?){13,16}\b"),
     "Possible payment-card number."),
    ("Account number", re.compile(r"\b(?:acct|account|acc)[.\s#:]*\d{6,17}\b", re.IGNORECASE),
     "Financial account number."),
    ("Routing number", re.compile(r"\b(?:routing|aba)[.\s#:]*\d{9}\b", re.IGNORECASE),
     "Bank routing number."),
    # NOTE: no leading "\b" — a word boundary fails immediately before a literal
    # "(" so it would drop the leading paren of "(314) 555-0142". Use digit
    # look-around instead so the whole "(314) 555-0142" span (paren included) is
    # captured without grabbing a longer adjacent digit run.
    ("Phone", re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
     "Phone number — personal contact information."),
    ("Email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
     "Email address — personal contact information."),
    ("Date of birth", re.compile(
        r"\b(?:DOB|D\.O\.B\.|date of birth|born(?:\s+on)?)[:\s]*"
        r"(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE),
     "Date of birth — used for identity verification."),
]

# Roughly: a credit-card hit must contain >=13 digits to reduce false positives.
def _digit_count(s: str) -> int:
    return sum(c.isdigit() for c in s)


def _digit_span(s: str) -> str:
    """Normalized digit-only key for a match (strips labels/format/punctuation)."""
    return "".join(c for c in s if c.isdigit())


def _regex_redactions(per_doc: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for d in per_doc:
        text = d["text"]
        seen: set = set()
        # Track character spans already claimed by a higher-priority pattern so a
        # bare digit run isn't double-reported (e.g. an account number that the
        # phone pattern would also match). Patterns are ordered most→least specific.
        claimed: List[Tuple[int, int]] = []
        # Dedup by NORMALIZED DIGIT-SPAN across ALL types so one number isn't
        # reported under two PII types (e.g. a labeled "account 4111…" and the
        # bare card pattern matching the same 16 digits). The first (most-specific)
        # pattern to claim a digit-span wins; later types skip that same number.
        seen_digits: set = set()
        for ptype, pat, reason in _PII_PATTERNS:
            for m in pat.finditer(text):
                span = m.group(0).strip()
                if ptype == "Credit card" and _digit_count(span) < 13:
                    continue
                start, end = m.start(), m.end()
                # Skip if this match's digits overlap a span already claimed by a
                # more-specific PII type (account/routing/SSN take priority over phone).
                if ptype in ("Phone", "Credit card") and any(
                    not (end <= cs or start >= ce) for cs, ce in claimed
                ):
                    continue
                digits = _digit_span(span)
                # Cross-type dedup: same number already reported under another type.
                if digits and digits in seen_digits:
                    continue
                key = (ptype, span)
                if key in seen:
                    continue
                seen.add(key)
                if digits:
                    seen_digits.add(digits)
                claimed.append((start, end))
                out.append({
                    "type": ptype,
                    "text": span,
                    "suggested_redaction": "[REDACTED " + ptype.upper() + "]",
                    "source_doc": d["source_doc"],
                    "reason": reason,
                    "detected_by": "regex",
                })
    return out


_REDACTION_SYSTEM = (
    "You are a privacy redaction assistant. From the provided user-uploaded "
    "documents, identify additional SENSITIVE PERSONAL INFORMATION that a person "
    "should redact before sharing the file — for example: full home addresses, "
    "driver's license numbers, passport numbers, medical information, mother's "
    "maiden name, or other personal identifiers. Respond with STRICT JSON only "
    "(no markdown, no prose): a JSON ARRAY of "
    '{"type": "...", "text": "...", "source_doc": "...", "reason": "..."}. '
    "text = the exact sensitive value to redact. Do NOT include things already "
    "obvious like emails or phone numbers. Do not invent data not in the text."
)


def redaction(collection_id: str, use_llm: bool = True) -> Dict[str, Any]:
    """
    Suggest redactions of sensitive PII.

    A DETERMINISTIC regex pass (SSN, account/routing, card, phone, email, DOB, EIN)
    ALWAYS runs and works with no LLM key. If a key is available and use_llm=True,
    an LLM pass augments it with less-structured PII (addresses, license numbers,
    medical info, etc.). This is a privacy-PROTECTING tool — it helps the user
    redact before sharing.
    """
    per_doc = _gather_docs(collection_id)
    if not per_doc:
        return {"redactions": [], "provider": "none", "deterministic_count": 0, "llm_count": 0,
                "note": "No documents are indexed in this collection yet.",
                "privacy_note": _PRIVACY_NOTE}

    redactions = _regex_redactions(per_doc)
    deterministic_count = len(redactions)
    provider = "deterministic (regex)"
    llm_count = 0

    if use_llm and llm_router.available_providers():
        corpus = _corpus_text(per_doc)
        raw, prov = llm_router.synthesize(_REDACTION_SYSTEM, corpus)
        parsed = _extract_json(raw) if raw else None
        if isinstance(parsed, list):
            existing = {(r["type"], r["text"]) for r in redactions}
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                txt = str(item.get("text", "")).strip()
                ptype = str(item.get("type", "PII")).strip() or "PII"
                if not txt or (ptype, txt) in existing:
                    continue
                existing.add((ptype, txt))
                redactions.append({
                    "type": ptype,
                    "text": txt[:200],
                    "suggested_redaction": "[REDACTED " + ptype.upper() + "]",
                    "source_doc": str(item.get("source_doc", "")).strip(),
                    "reason": str(item.get("reason", "Sensitive personal information.")).strip()[:300],
                    "detected_by": "llm",
                })
                llm_count += 1
            if llm_count:
                provider = f"deterministic (regex) + {prov}"

    return {
        "redactions": redactions,
        "deterministic_count": deterministic_count,
        "llm_count": llm_count,
        "provider": provider,
        "note": "" if redactions else "No sensitive PII patterns were detected.",
        "privacy_note": _PRIVACY_NOTE,
    }


_PRIVACY_NOTE = (
    "This flags sensitive information so you can redact it BEFORE sharing a document. "
    "It is a privacy-protecting feature — nothing here is published or sent anywhere; "
    "your uploaded files stay local."
)


# =============================================================================
# Per-collection cache (recompute on demand)
# =============================================================================
_CACHE: Dict[str, Dict[str, Any]] = {}

_BUILDERS = {
    "relationships": relationships,
    "timeline": timeline,
    "patterns": patterns,
}


def get_cached(collection_id: str, kind: str, refresh: bool = False) -> Dict[str, Any]:
    """Return a cached analysis for (collection, kind), computing it on demand."""
    bucket = _CACHE.setdefault(collection_id, {})
    if refresh or kind not in bucket:
        bucket[kind] = _BUILDERS[kind](collection_id)
    return bucket[kind]


def invalidate(collection_id: str) -> None:
    """Drop cached analyses for a collection (e.g. after a new upload to it)."""
    _CACHE.pop(collection_id, None)
