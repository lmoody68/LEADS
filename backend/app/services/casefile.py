"""
Document / Case-File Analyzer (MasterBuildPlan §3.7) for L.E.A.D.S.

Ingests user-uploaded documents into a SEPARATE per-collection Chroma store
(casefile_<collection_id>), extracts entities, and answers cited questions over
the uploaded collection.

GUARDRAILS (NON-NEGOTIABLE):
- Works ONLY on user-uploaded documents. No web scraping. No PII harvesting.
- Uploaded / privileged docs stay LOCAL (Chroma persistent dir) and are NEVER
  published.
- The LLM router never trains on / retains any data (stateless completion calls).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List

from . import doc_analysis, llm_router, rag
from .docparse import parse_document

# --- Deterministic regex fallbacks (used when no LLM key) ---------------------
_DATE_RE = re.compile(
    r"\b("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r")\b"
)
# Common U.S. legal citation shapes: "15 U.S.C. § 1692c", "410 U.S. 113", "Fed. R. Civ. P. 12".
_CITATION_RE = re.compile(
    r"\b("
    r"\d+\s+U\.?S\.?C\.?\s+§*\s*\d+[a-z]?(?:\([0-9a-zA-Z]+\))*"
    r"|\d+\s+U\.?S\.?\s+\d+"
    r"|Fed\.\s*R\.\s*(?:Civ|Crim|Evid|App)\.\s*P\.\s*\d+"
    r")\b"
)


def _collection_name(collection_id: str) -> str:
    return f"casefile_{collection_id}"


def _regex_entities(text: str) -> Dict[str, List[str]]:
    """Deterministic fallback entity extraction for dates + legal citations."""
    dates = sorted({m.group(1).strip() for m in _DATE_RE.finditer(text)})
    citations = sorted({m.group(1).strip() for m in _CITATION_RE.finditer(text)})
    return {
        "people": [],
        "organizations": [],
        "locations": [],
        "dates": dates,
        "legal_citations": citations,
    }


_ENTITY_SYSTEM = (
    "You are an entity-extraction engine for a legal case-file analyzer. From the "
    "user-provided document text, extract entities. Respond with STRICT JSON only "
    "(no markdown, no prose) of the form: "
    '{"people": [], "organizations": [], "locations": [], "dates": [], "legal_citations": []}. '
    "Each value is a list of unique strings found in the text. Do not invent entities."
)


def _extract_json(raw: str) -> Dict[str, Any] | None:
    """Pull a JSON object out of an LLM response that may wrap it in fences/prose."""
    if not raw:
        return None
    # Strip code fences if present.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    # Otherwise grab the first balanced-looking {...} span.
    if not fenced:
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = brace.group(0) if brace else candidate
    try:
        return json.loads(candidate)
    except Exception:
        return None


def extract_entities(text: str) -> Dict[str, List[str]]:
    """
    Entity extraction via the LLM router (JSON), with a deterministic regex
    fallback for dates + citations when no LLM key is configured or the LLM
    output can't be parsed.
    """
    # Cap the text sent to the LLM to keep the request bounded.
    sample = text[:12000]
    out, _provider = llm_router.synthesize(_ENTITY_SYSTEM, sample)
    parsed = _extract_json(out) if out else None

    fallback = _regex_entities(text)
    if not parsed:
        return fallback

    # Normalize and merge the regex-found dates/citations in case the LLM missed any.
    result: Dict[str, List[str]] = {}
    for key in ("people", "organizations", "locations", "dates", "legal_citations"):
        vals = parsed.get(key, []) or []
        if not isinstance(vals, list):
            vals = [str(vals)]
        merged = {str(v).strip() for v in vals if str(v).strip()}
        merged |= set(fallback.get(key, []))
        result[key] = sorted(merged)
    return result


def ingest_upload(filename: str, data: bytes, collection_id: str | None = None) -> Dict[str, Any]:
    """
    Parse + chunk + embed an uploaded document into its own Chroma collection,
    and extract an entity outline. Returns {collection_id, chunks, entities, note}.
    """
    collection_id = collection_id or uuid.uuid4().hex[:12]
    col_name = _collection_name(collection_id)

    text, note = parse_document(filename, data)
    if not text:
        return {
            "collection_id": collection_id,
            "chunks": 0,
            "entities": _regex_entities(""),
            "note": note or "No text could be extracted from the document.",
        }

    chunks = rag.ingest(
        [{"source_title": filename, "citation": filename, "section": filename, "text": text}],
        collection_name=col_name,
    )
    # A new document changed this collection — drop any cached cross-doc analyses.
    doc_analysis.invalidate(collection_id)
    entities = extract_entities(text)

    return {
        "collection_id": collection_id,
        "chunks": chunks,
        "entities": entities,
        "note": note,
    }


def get_entities(collection_id: str) -> Dict[str, List[str]]:
    """Re-derive the entity outline from all stored chunks of a collection."""
    col = rag.get_collection(_collection_name(collection_id))
    if col.count() == 0:
        return _regex_entities("")
    got = col.get()
    full_text = "\n".join(got.get("documents", []) or [])
    return extract_entities(full_text)


def answer(question: str, collection_id: str, k: int = 4) -> Dict[str, Any]:
    """Cited RAG answer over a single uploaded case-file collection."""
    return rag.answer(question, k=k, collection_name=_collection_name(collection_id))
