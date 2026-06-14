"""
RAG Deep-Research Engine (MasterBuildPlan §3.1) for L.E.A.D.S.

Direct chunk -> embed -> retrieve -> LLM flow (NO LangChain in Phase 0 — the
agentic memo is a later phase). ChromaDB persistent client with Chroma's DEFAULT
embedding function (all-MiniLM-L6-v2 via onnxruntime — the model the plan names,
with no torch dependency).

GUARDRAIL: The seed corpus is PUBLIC, licensed U.S. legal text only (FDCPA,
FCRA, DPPA, GLBA). Everything persists to a LOCAL ./chroma_db directory and is
never published.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.utils import embedding_functions

from . import llm_router

# --- Paths -------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
CHROMA_DIR = os.getenv("CHROMA_DIR", str(_BACKEND_ROOT / "chroma_db"))
SEED_CORPUS_DIR = _BACKEND_ROOT / "app" / "data" / "seed_corpus"

LEGAL_COLLECTION = "legal_seed_corpus"

# Chroma's default embedding function = sentence-transformers/all-MiniLM-L6-v2,
# served via onnxruntime (no torch).
_EMBED_FN = embedding_functions.DefaultEmbeddingFunction()

_client = chromadb.PersistentClient(path=CHROMA_DIR)


def get_collection(name: str = LEGAL_COLLECTION):
    return _client.get_or_create_collection(name=name, embedding_function=_EMBED_FN)


# --- Legal-aware chunking ----------------------------------------------------
def chunk_text(text: str, max_chars: int = 1200) -> List[str]:
    """
    Legal-aware-ish chunking: split on paragraph/sentence boundaries and pack
    into chunks up to ~max_chars so a single subsection's clauses stay together.
    """
    text = text.strip()
    if not text:
        return []
    # Split on blank lines first, then on sentence boundaries within long blocks.
    paragraphs = re.split(r"\n\s*\n", text)
    pieces: List[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            pieces.append(para)
        else:
            # Break long statutory text on enumerated clause boundaries / sentences.
            sentences = re.split(r"(?<=[.;])\s+(?=\([0-9a-zA-Z]\)|[A-Z])", para)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) + 1 > max_chars and buf:
                    pieces.append(buf.strip())
                    buf = s
                else:
                    buf = f"{buf} {s}".strip()
            if buf:
                pieces.append(buf.strip())
    return pieces


def ingest(docs: List[Dict[str, Any]], collection_name: str = LEGAL_COLLECTION) -> int:
    """
    Ingest documents into a Chroma collection.

    Each doc: {source_title, citation/section, text}. Returns number of chunks added.
    Metadata stored per chunk: source_title, citation, section, chunk_id.
    """
    col = get_collection(collection_name)
    ids: List[str] = []
    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for doc in docs:
        source_title = doc.get("source_title", "Untitled")
        citation = doc.get("citation", "")
        section = doc.get("section", citation)
        base_id = doc.get("id") or re.sub(r"[^a-zA-Z0-9]+", "_", f"{citation}_{section}").strip("_")
        for i, chunk in enumerate(chunk_text(doc["text"])):
            chunk_id = f"{base_id}::chunk{i}"
            ids.append(chunk_id)
            texts.append(chunk)
            metadatas.append(
                {
                    "source_title": source_title,
                    "citation": citation,
                    "section": section,
                    "chunk_id": chunk_id,
                }
            )

    if ids:
        col.upsert(ids=ids, documents=texts, metadatas=metadatas)
    return len(ids)


def _load_seed_docs() -> List[Dict[str, Any]]:
    """Flatten the seed_corpus JSON files into per-section ingest docs."""
    docs: List[Dict[str, Any]] = []
    for path in sorted(SEED_CORPUS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        source_title = data["source_title"]
        for sec in data["sections"]:
            heading = sec.get("heading", "")
            docs.append(
                {
                    "source_title": source_title,
                    "citation": data["citation"],
                    "section": sec["section"],
                    "text": f"{heading}. {sec['text']}" if heading else sec["text"],
                }
            )
    return docs


def ensure_seed_ingested() -> int:
    """
    Idempotently ingest the legal seed corpus at startup. If the collection
    already holds the seed sections, do nothing. Returns total chunks in collection.
    """
    col = get_collection(LEGAL_COLLECTION)
    seed_docs = _load_seed_docs()
    if col.count() == 0:
        ingest(seed_docs, LEGAL_COLLECTION)
    return col.count()


# --- Retrieval ---------------------------------------------------------------
def retrieve(query: str, k: int = 4, collection_name: str = LEGAL_COLLECTION) -> List[Dict[str, Any]]:
    col = get_collection(collection_name)
    n = col.count()
    if n == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(k, n))
    out: List[Dict[str, Any]] = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        # Chroma returns L2/cosine distance; convert to a 0..1 relevance score.
        score = round(1.0 / (1.0 + float(dist)), 4)
        out.append(
            {
                "source_title": meta.get("source_title", ""),
                "citation": meta.get("citation", meta.get("section", "")),
                "section": meta.get("section", ""),
                "snippet": doc,
                "score": score,
            }
        )
    return out


# --- Citation-grounded answer ------------------------------------------------
_SYSTEM_PROMPT = (
    "You are L.E.A.D.S., a legal research assistant. Answer the user's question "
    "USING ONLY the numbered passages provided. Ground every assertion in those "
    "passages and cite the statute citation in brackets, e.g. [15 U.S.C. § 1692c(b)]. "
    "If the passages do not fully cover the question, say so explicitly and do not "
    "speculate beyond them. Be precise and concise. This is general legal "
    "information, not legal advice."
)


def _format_passages(hits: List[Dict[str, Any]]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(
            f"[{i}] Source: {h['source_title']}\n"
            f"    Citation: {h['citation']}\n"
            f"    Passage: {h['snippet']}"
        )
    return "\n\n".join(lines)


def _extractive_answer(question: str, hits: List[Dict[str, Any]]) -> str:
    """
    Fallback when no LLM is available: return the top passages verbatim as the
    answer, each tagged with its citation. The app stays fully functional and
    every statement is grounded + cited.
    """
    parts = [
        "No LLM provider key is configured, so the following are the most "
        "relevant statutory passages retrieved for your question (extractive mode):",
        "",
    ]
    for i, h in enumerate(hits, 1):
        parts.append(f"{i}. [{h['citation']}] — {h['source_title']}")
        parts.append(f"   {h['snippet']}")
        parts.append("")
    return "\n".join(parts).strip()


def answer(
    question: str,
    k: int = 4,
    collection_name: str = LEGAL_COLLECTION,
) -> Dict[str, Any]:
    """
    Full RAG: retrieve -> (LLM synthesize | extractive fallback). Returns
    {answer, citations:[{source_title, citation, snippet, score}], provider}.
    """
    hits = retrieve(question, k=k, collection_name=collection_name)
    if not hits:
        return {
            "answer": "No documents are indexed yet, so there is nothing to ground an answer on.",
            "citations": [],
            "provider": "none",
        }

    user_prompt = (
        f"Question: {question}\n\n"
        f"Passages:\n{_format_passages(hits)}\n\n"
        "Answer the question using only these passages, citing each one you rely on."
    )
    text, provider = llm_router.synthesize(_SYSTEM_PROMPT, user_prompt)
    if text is None:
        text = _extractive_answer(question, hits)

    return {"answer": text, "citations": hits, "provider": provider}
