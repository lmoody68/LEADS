"""
Public Legal-Dataset Discovery (MasterBuildPlan §3.8 / Phase 7) for L.E.A.D.S.

Adapted from the N.O.V.A.S. `dataset_discovery_agent` pattern (a discovery agent
over public dataset repos), re-scoped to LEGAL datasets and hardened with a
PII / people-search filter.

=============================================================================
GUARDRAILS — GUARDRAIL-CRITICAL. READ BEFORE EDITING.
=============================================================================
  * PUBLIC dataset repositories ONLY, via their OFFICIAL listing APIs:
      - Hugging Face Hub (huggingface_hub.list_datasets — no auth needed for
        public listing).
      - Kaggle (official kaggle API — OPTIONAL; gracefully skipped if no
        kaggle.json credentials are present).
    No scraping, no bot-protection bypass, no rate-limit evasion, honest
    User-Agent (the underlying clients set their own).

  * PUBLIC / LICENSED LEGAL DATA ONLY. We surface datasets of legal TEXT
    (statutes, case law, contracts, legal QA/benchmarks). We DO NOT surface
    people-search or PII datasets.

  * PII FILTER (mandatory): every candidate is screened with `is_pii_risk()`.
    Anything that looks like personal data / people-search (voter files, court
    *records* about named individuals, addresses, criminal-history, doxxing,
    facial / biometric, leaked-credential dumps, etc.) is FLAGGED with
    `is_pii_risk: true`. The ingest endpoint REFUSES to pull a PII-risk dataset
    into the corpus.

  * Dataset ingestion is LIGHTWEIGHT — a SMALL streamed sample (first N rows),
    never a full training download. The `datasets` library is an OPTIONAL,
    LAZY import: if it is not installed, we register the dataset's metadata only
    so the app still boots and the discovery feature still works.
=============================================================================
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import rag

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
_DATASETS_STORE = _BACKEND_ROOT / "datasets_store"  # metadata for registered datasets


# --- PII / people-search risk filter -----------------------------------------
# If ANY of these signals appear in the dataset id / description, we flag it as a
# personal-data risk and refuse to ingest it. Conservative by design (false
# positives are acceptable; ingesting PII is NOT).
_PII_SIGNALS = [
    "people search", "people-search", "person search", "background check",
    "voter", "voters", "voter file", "address", "addresses", "phone number",
    "phone-number", "ssn", "social security", "criminal record", "criminal-record",
    "arrest record", "mugshot", "inmate", "offender", "sex offender",
    "personal data", "personal-information", "pii", "doxx", "dox ",
    "biometric", "facial", "face dataset", "fingerprint", "passport",
    "driver license", "drivers license", "driver's license", "national id",
    "credit card", "bank account", "medical record", "patient", "health record",
    "leaked", "breach", "credentials", "password dump", "email list",
    "contact list", "phone book", "phonebook", "genealogy", "ancestry",
    "date of birth", "dob dataset",
]

# Positive legal signals — help rank/justify legal relevance.
_LEGAL_SIGNALS = [
    "legal", "law", "court", "opinion", "case law", "caselaw", "statute",
    "regulation", "contract", "litigation", "judicial", "judgment", "judgement",
    "scotus", "supreme court", "appeal", "docket", "code of federal",
    "u.s. code", "usc", "cfr", "legislation", "bill", "pile-of-law",
    "legalbench", "eurlex", "eur-lex", "casehold", "ledgar", "cuad",
]


def is_pii_risk(name: str, description: str) -> bool:
    """
    True if a dataset looks like personal-data / people-search content that must
    NOT be ingested. Errs on the side of caution.
    """
    blob = f"{name} {description}".lower()
    return any(sig in blob for sig in _PII_SIGNALS)


def _looks_legal(name: str, description: str) -> bool:
    blob = f"{name} {description}".lower()
    return any(sig in blob for sig in _LEGAL_SIGNALS)


# --- Hugging Face Hub discovery (official listing API, no auth) ---------------
def _discover_huggingface(query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        from huggingface_hub import list_datasets  # official client
    except Exception as exc:  # pragma: no cover
        print(f"[dataset_discovery] huggingface_hub unavailable: {exc}")
        return []

    out: List[Dict[str, Any]] = []
    try:
        # `search` does a public keyword search over the Hub. No auth required.
        results = list_datasets(search=query or "legal", limit=max(limit * 3, 15), full=True)
    except Exception as exc:
        print(f"[dataset_discovery] HF list_datasets failed: {exc}")
        return []

    for d in results:
        ds_id = getattr(d, "id", "") or ""
        card = getattr(d, "card_data", None)
        description = ""
        license_str = ""
        if card is not None:
            # card_data may be a dict-like with 'license' / pretty_name etc.
            try:
                license_str = (card.get("license") if hasattr(card, "get") else getattr(card, "license", "")) or ""
                if isinstance(license_str, list):
                    license_str = ", ".join(str(x) for x in license_str)
            except Exception:
                license_str = ""
        # Tags often carry a "license:..." marker.
        tags = getattr(d, "tags", None) or []
        if not license_str:
            for t in tags:
                if isinstance(t, str) and t.startswith("license:"):
                    license_str = t.split(":", 1)[1]
                    break
        description = (getattr(d, "description", None) or "").strip()
        if not description and tags:
            description = ", ".join(t for t in tags if isinstance(t, str))[:300]

        pii = is_pii_risk(ds_id, description + " " + " ".join(str(t) for t in tags))
        out.append(
            {
                "name": ds_id,
                "source": "huggingface",
                "description": (description or "(no description provided)")[:400],
                "downloads": int(getattr(d, "downloads", 0) or 0),
                "url": f"https://huggingface.co/datasets/{ds_id}",
                "license": license_str or "unspecified",
                "is_pii_risk": pii,
                "legal_relevant": _looks_legal(ds_id, description),
            }
        )

    # Rank: legal-relevant + non-PII + downloads.
    out.sort(key=lambda r: (r["legal_relevant"], not r["is_pii_risk"], r["downloads"]), reverse=True)
    return out[:limit]


# --- Kaggle discovery (official API, OPTIONAL / graceful) --------------------
def _discover_kaggle(query: str, limit: int) -> List[Dict[str, Any]]:
    """
    Use the official kaggle API if credentials (kaggle.json / env) are present.
    Returns [] gracefully if kaggle isn't installed or no creds are configured —
    NEVER prompts and NEVER scrapes the Kaggle website.
    """
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore
    except Exception:
        return []
    try:
        api = KaggleApi()
        api.authenticate()  # raises if no kaggle.json / env creds
    except Exception as exc:
        print(f"[dataset_discovery] Kaggle creds absent/invalid — skipping gracefully: {exc}")
        return []

    out: List[Dict[str, Any]] = []
    try:
        datasets = api.dataset_list(search=query or "legal", max_size=None)
    except Exception as exc:
        print(f"[dataset_discovery] Kaggle search failed: {exc}")
        return []

    for d in (datasets or [])[: max(limit * 2, 10)]:
        ref = getattr(d, "ref", "") or str(d)
        title = getattr(d, "title", "") or ref
        subtitle = getattr(d, "subtitle", "") or ""
        lic = getattr(d, "licenseName", "") or "unspecified"
        dls = int(getattr(d, "downloadCount", 0) or 0)
        description = f"{title}. {subtitle}".strip()
        pii = is_pii_risk(f"{ref} {title}", subtitle)
        out.append(
            {
                "name": ref,
                "source": "kaggle",
                "description": description[:400],
                "downloads": dls,
                "url": f"https://www.kaggle.com/datasets/{ref}",
                "license": lic,
                "is_pii_risk": pii,
                "legal_relevant": _looks_legal(f"{ref} {title}", subtitle),
            }
        )
    out.sort(key=lambda r: (r["legal_relevant"], not r["is_pii_risk"], r["downloads"]), reverse=True)
    return out[:limit]


def discover(query: str = "legal", limit: int = 12) -> Dict[str, Any]:
    """
    Search public dataset repos (HF Hub + optional Kaggle) for LEGAL datasets.

    Returns {query, results:[{name, source, description, downloads, url, license,
    is_pii_risk, legal_relevant}], pii_flagged, sources_searched}.
    """
    query = (query or "legal").strip()
    limit = max(1, min(int(limit or 12), 40))

    hf = _discover_huggingface(query, limit)
    kaggle = _discover_kaggle(query, max(limit // 2, 4))

    results = hf + kaggle
    # Final ordering across sources.
    results.sort(key=lambda r: (r["legal_relevant"], not r["is_pii_risk"], r["downloads"]), reverse=True)
    results = results[:limit]

    sources_searched = ["huggingface"]
    if kaggle:
        sources_searched.append("kaggle")

    return {
        "query": query,
        "results": results,
        "pii_flagged": sum(1 for r in results if r["is_pii_risk"]),
        "sources_searched": sources_searched,
        "note": (
            "Kaggle is included only if kaggle.json credentials are present "
            "(official API, no scraping)." if not kaggle else ""
        ),
    }


# --- Lightweight sample ingestion --------------------------------------------
def _find_text_field(row: Dict[str, Any]) -> Optional[str]:
    """Pick the most text-like column from a dataset row."""
    candidates = ["text", "opinion", "content", "document", "body", "passage",
                  "case", "answer", "question", "context", "article", "clause"]
    for c in candidates:
        if c in row and isinstance(row[c], str) and row[c].strip():
            return row[c]
    # Else: the longest string field.
    best = ""
    for v in row.values():
        if isinstance(v, str) and len(v) > len(best):
            best = v
    return best or None


def ingest_dataset(dataset_id: str, source: str = "huggingface", sample_rows: int = 10) -> Dict[str, Any]:
    """
    Pull a SMALL sample of a chosen PUBLIC LEGAL dataset into the corpus (or, if
    the `datasets` lib is unavailable, register its metadata in datasets_store/).

    GUARDRAIL: refuses PII-risk datasets. Keeps it lightweight — a streamed
    sample, never a full training download.

    Returns {dataset_id, source, ingested_rows, added_chunks, corpus_size_before,
             corpus_size_after, mode, note}.
    """
    dataset_id = (dataset_id or "").strip()
    if not dataset_id:
        return {"error": "dataset_id is required"}

    # Re-screen for PII at ingestion time (defense-in-depth).
    if is_pii_risk(dataset_id, ""):
        return {
            "dataset_id": dataset_id,
            "source": source,
            "ingested_rows": 0,
            "added_chunks": 0,
            "mode": "refused",
            "note": "Refused: dataset id matches a personal-data / people-search signal. "
                    "L.E.A.D.S. ingests public legal text only — no PII datasets.",
        }

    sample_rows = max(1, min(int(sample_rows or 10), 50))
    col = rag.get_collection(rag.LEGAL_COLLECTION)
    size_before = col.count()

    if source != "huggingface":
        # Kaggle datasets aren't streamable row-by-row without a full download —
        # register metadata only (lightweight) for later aux-classifier use.
        return _register_metadata(dataset_id, source, size_before,
                                  note="Non-HF source: metadata registered (no full download).")

    # Lazy, guarded import so the app boots without `datasets` installed.
    try:
        from datasets import load_dataset  # type: ignore
    except Exception:
        return _register_metadata(
            dataset_id, source, size_before,
            note="The 'datasets' library is not installed; registered metadata only. "
                 "Install 'datasets' to pull a live sample.",
        )

    rows: List[Dict[str, Any]] = []
    try:
        ds = load_dataset(dataset_id, split="train", streaming=True)
        for i, row in enumerate(ds):
            if i >= sample_rows:
                break
            rows.append(row)
    except Exception as exc:
        # Many datasets need a config name; try without a split, else register.
        try:
            ds = load_dataset(dataset_id, streaming=True)
            first_split = next(iter(ds.keys())) if hasattr(ds, "keys") else None
            if first_split:
                for i, row in enumerate(ds[first_split]):
                    if i >= sample_rows:
                        break
                    rows.append(row)
        except Exception as exc2:
            return _register_metadata(
                dataset_id, source, size_before,
                note=f"Could not stream a sample ({type(exc).__name__}/{type(exc2).__name__}); "
                     "registered metadata only.",
            )

    docs: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        text = _find_text_field(row)
        if not text or not text.strip():
            continue
        safe_id = re.sub(r"[^a-zA-Z0-9]+", "_", dataset_id)[:50]
        docs.append(
            {
                "id": f"hf_{safe_id}_{i}",
                "source_title": f"{dataset_id} (sample row {i})",
                "citation": f"HF dataset · {dataset_id}",
                "section": "dataset_sample",
                "doc_type": "dataset_sample",
                "court": "",
                "date": "",
                "url": f"https://huggingface.co/datasets/{dataset_id}",
                "text": text[:8000],
            }
        )

    added = 0
    if docs:
        rag.ingest(docs, rag.LEGAL_COLLECTION)
        added = sum(len(rag.chunk_text(d["text"])) for d in docs)

    size_after = col.count()
    return {
        "dataset_id": dataset_id,
        "source": source,
        "ingested_rows": len(docs),
        "added_chunks": size_after - size_before,
        "corpus_size_before": size_before,
        "corpus_size_after": size_after,
        "mode": "sampled",
        "note": f"Ingested a {len(docs)}-row sample (streaming, lightweight).",
    }


def _register_metadata(dataset_id: str, source: str, size_before: int, note: str) -> Dict[str, Any]:
    """Persist dataset metadata to datasets_store/ for later aux use (no corpus change)."""
    try:
        _DATASETS_STORE.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", f"{source}_{dataset_id}")[:80]
        (_DATASETS_STORE / f"{safe}.json").write_text(
            __import__("json").dumps({"dataset_id": dataset_id, "source": source, "note": note}),
            encoding="utf-8",
        )
    except Exception:
        pass
    return {
        "dataset_id": dataset_id,
        "source": source,
        "ingested_rows": 0,
        "added_chunks": 0,
        "corpus_size_before": size_before,
        "corpus_size_after": size_before,
        "mode": "metadata_only",
        "note": note,
    }
