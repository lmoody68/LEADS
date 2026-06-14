"""
RAG Deep-Research Engine (MasterBuildPlan §3.1) for L.E.A.D.S.

Phase 1 upgrade: hybrid retrieval (dense Chroma embeddings + sparse BM25 fused
with Reciprocal Rank Fusion), on-demand ingestion of LIVE CourtListener case law
alongside the seeded statutes, legal-aware chunking (syllabus/holding/facts/
dissent), and a citation-grounded answer with conflict detection, a grounding
note, and follow-up suggestions.

Chroma uses its DEFAULT embedding function (all-MiniLM-L6-v2 via onnxruntime —
the model the plan names, with no torch dependency).

GUARDRAILS:
- Seed corpus = PUBLIC, licensed U.S. legal text only (FDCPA, FCRA, DPPA, GLBA).
- Live case law = PUBLIC court opinions via the CourtListener REST API (no
  scraping, no PII).
- Everything persists to a LOCAL ./chroma_db dir and is never published.
- The LLM router makes stateless calls — nothing trains on the data.
- If no LLM key and/or no network: the pipeline degrades gracefully (deterministic
  planner + extractive, still-cited answer over whatever corpus is available).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

from . import courtlistener, llm_router, query_planner, reranker

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
# Markers that, when present in an opinion, signal a structural section. We tag
# each chunk with the section it belongs to so retrieval/answer can surface
# e.g. the holding vs. a dissent.
_SECTION_MARKERS = [
    ("syllabus", re.compile(r"^\s*syllabus\b", re.IGNORECASE | re.MULTILINE)),
    ("holding", re.compile(r"\b(we (?:hold|conclude|affirm|reverse|remand)|held that|it is so ordered)\b", re.IGNORECASE)),
    ("dissent", re.compile(r"\b(dissent(?:ing)?|concur(?:ring)? in part)\b", re.IGNORECASE)),
    ("facts", re.compile(r"\b(factual background|statement of facts|the facts\b|background\b)", re.IGNORECASE)),
]


def _label_section(chunk: str) -> str:
    """Best-effort legal section label for an opinion chunk (else 'opinion')."""
    for label, pat in _SECTION_MARKERS:
        if pat.search(chunk):
            return label
    return "opinion"


def chunk_text(text: str, max_chars: int = 1200) -> List[str]:
    """
    Legal-aware-ish chunking: split on paragraph/sentence boundaries and pack
    into chunks up to ~max_chars so a single subsection's clauses stay together.
    """
    text = text.strip()
    if not text:
        return []
    paragraphs = re.split(r"\n\s*\n", text)
    pieces: List[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            pieces.append(para)
        else:
            # Break long text on enumerated clause boundaries / sentences.
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

    Each doc: {source_title, citation/section, text, [court], [date], [url],
    [doc_type]}. Returns number of chunks added. For opinion docs (doc_type ==
    'opinion') each chunk is also tagged with a legal section label.
    """
    col = get_collection(collection_name)
    ids: List[str] = []
    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for doc in docs:
        source_title = doc.get("source_title", "Untitled")
        citation = doc.get("citation", "")
        section = doc.get("section", citation)
        doc_type = doc.get("doc_type", "statute")
        court = doc.get("court", "")
        date = doc.get("date", "")
        url = doc.get("url", "")
        base_id = doc.get("id") or re.sub(r"[^a-zA-Z0-9]+", "_", f"{citation}_{section}").strip("_")
        for i, chunk in enumerate(chunk_text(doc["text"])):
            chunk_id = f"{base_id}::chunk{i}"
            label = _label_section(chunk) if doc_type == "opinion" else section
            ids.append(chunk_id)
            texts.append(chunk)
            metadatas.append(
                {
                    "source_title": source_title,
                    "citation": citation,
                    "section": section,
                    "chunk_id": chunk_id,
                    "doc_type": doc_type,
                    "court": court,
                    "date": date,
                    "url": url,
                    "legal_section": label,
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
                    "doc_type": "statute",
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


# --- On-demand CourtListener ingestion ---------------------------------------
def ingest_courtlistener(search_query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Fetch live opinions from CourtListener for `search_query`, chunk + embed them
    into the shared legal collection (so hybrid retrieval covers statutes AND
    fetched case law), and return the list of opinions ingested (for logging /
    transparency). Returns [] gracefully on any failure.
    """
    opinions = courtlistener.search_opinions(search_query, max_results=max_results)
    if not opinions:
        return []

    docs: List[Dict[str, Any]] = []
    for op in opinions:
        # Cap opinion text so a single mega-opinion doesn't dominate the index.
        text = (op.get("text") or "")[:40000]
        if not text.strip():
            continue
        docs.append(
            {
                "id": "cl_" + re.sub(r"[^a-zA-Z0-9]+", "_", (op.get("url") or op.get("case_name") or "op"))[:60],
                "source_title": op.get("case_name", "Court opinion"),
                "citation": op.get("citation") or op.get("case_name", ""),
                "section": op.get("citation") or op.get("case_name", ""),
                "doc_type": "opinion",
                "court": op.get("court", ""),
                "date": op.get("date", ""),
                "url": op.get("url", ""),
                "text": text,
            }
        )
    if docs:
        ingest(docs, LEGAL_COLLECTION)
    return opinions


# --- Hybrid retrieval: dense + BM25 + RRF ------------------------------------
def _hit_from_meta(doc: str, meta: Dict[str, Any], score: float) -> Dict[str, Any]:
    return {
        "source_title": meta.get("source_title", ""),
        "citation": meta.get("citation", meta.get("section", "")),
        "section": meta.get("section", ""),
        "court": meta.get("court", ""),
        "date": meta.get("date", ""),
        "url": meta.get("url", ""),
        "doc_type": meta.get("doc_type", "statute"),
        "legal_section": meta.get("legal_section", ""),
        "snippet": doc,
        "score": round(float(score), 4),
    }


def _dense_ranked(query: str, col, pool: int) -> List[Tuple[str, Dict[str, Any], float]]:
    """Dense semantic retrieval -> ranked [(doc, meta, relevance)]."""
    n = col.count()
    if n == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(pool, n))
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        rel = 1.0 / (1.0 + float(dist))  # distance -> 0..1 relevance
        out.append((doc, meta, rel))
    return out


_TOKEN_RE = re.compile(r"[a-z0-9§]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def _bm25_ranked(query: str, col, pool: int) -> List[Tuple[str, Dict[str, Any], float]]:
    """Sparse BM25 retrieval over the WHOLE collection -> ranked top `pool`."""
    got = col.get()  # all docs + metadata
    docs = got.get("documents", []) or []
    metas = got.get("metadatas", []) or []
    if not docs:
        return []
    tokenized_corpus = [_tokenize(d) for d in docs]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))
    ranked_idx = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:pool]
    return [(docs[i], metas[i], float(scores[i])) for i in ranked_idx if scores[i] > 0]


def hybrid_retrieve(
    query: str,
    k: int = 5,
    collection_name: str = LEGAL_COLLECTION,
    rrf_k: int = 60,
    rerank: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hybrid retrieval = dense (Chroma embeddings) + sparse (BM25), fused with
    Reciprocal Rank Fusion (RRF): score(d) = sum_over_rankers 1/(rrf_k + rank_d).
    When a cross-encoder reranker is available, the fused top candidates are
    re-scored jointly against the query and the best k are returned (a precision
    boost on top of RRF recall); otherwise the RRF order is used.

    Returns (hits, debug) where debug exposes per-ranker top results so callers
    can prove hybrid retrieval actually ran.
    """
    col = get_collection(collection_name)
    if col.count() == 0:
        return [], {"dense_top": [], "bm25_top": [], "fused": 0, "reranked": False}

    pool = max(k * 3, 12)
    dense = _dense_ranked(query, col, pool)
    sparse = _bm25_ranked(query, col, pool)

    # Build per-chunk RRF fusion keyed by chunk_id (fall back to snippet hash).
    fused: Dict[str, Dict[str, Any]] = {}

    def _key(meta: Dict[str, Any], doc: str) -> str:
        return meta.get("chunk_id") or str(hash(doc))

    for rank, (doc, meta, _rel) in enumerate(dense):
        key = _key(meta, doc)
        entry = fused.setdefault(key, {"doc": doc, "meta": meta, "rrf": 0.0, "dense_rank": None, "bm25_rank": None})
        entry["rrf"] += 1.0 / (rrf_k + rank + 1)
        entry["dense_rank"] = rank + 1

    for rank, (doc, meta, _sc) in enumerate(sparse):
        key = _key(meta, doc)
        entry = fused.setdefault(key, {"doc": doc, "meta": meta, "rrf": 0.0, "dense_rank": None, "bm25_rank": None})
        entry["rrf"] += 1.0 / (rrf_k + rank + 1)
        entry["bm25_rank"] = rank + 1

    # Rank by RRF, then rerank a larger candidate pool down to k with the
    # cross-encoder (graceful no-op if the reranker is unavailable).
    ranked_all = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)
    rerank_pool = max(k * 4, 20)
    ranked = ranked_all[:rerank_pool]
    pool_hits = [_hit_from_meta(e["doc"], e["meta"], e["rrf"]) for e in ranked]

    reranked = False
    if rerank and reranker.available():
        hits = reranker.rerank(query, pool_hits, top_k=k)
        reranked = any("rerank_score" in h for h in hits)
    else:
        hits = pool_hits[:k]

    # RRF top-k (pre-rerank) for transparency in the debug panel.
    rrf_top_k = ranked[:k]
    debug = {
        "dense_top": [
            {"citation": m.get("citation", ""), "section": m.get("legal_section", m.get("section", "")), "rel": round(r, 4)}
            for (_d, m, r) in dense[:5]
        ],
        "bm25_top": [
            {"citation": m.get("citation", ""), "section": m.get("legal_section", m.get("section", "")), "bm25": round(s, 3)}
            for (_d, m, s) in sparse[:5]
        ],
        "fused": len(fused),
        "reranked": reranked,
        "rerank_pool": len(pool_hits),
        "fused_top": [
            {
                "citation": _hit_from_meta(e["doc"], e["meta"], e["rrf"])["citation"],
                "dense_rank": e["dense_rank"],
                "bm25_rank": e["bm25_rank"],
                "rrf": round(e["rrf"], 5),
            }
            for e in rrf_top_k
        ],
    }
    return hits, debug


def retrieve(query: str, k: int = 4, collection_name: str = LEGAL_COLLECTION) -> List[Dict[str, Any]]:
    """Back-compat dense-only retrieval (used by the casefile analyzer)."""
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
        score = round(1.0 / (1.0 + float(dist)), 4)
        out.append(_hit_from_meta(doc, meta, score))
    return out


# --- Citation-grounded answer (Phase 1) --------------------------------------
_SYSTEM_PROMPT = (
    "You are L.E.A.D.S., a legal research assistant. Answer the user's question "
    "USING ONLY the numbered passages provided (statutes and court opinions). "
    "Ground every assertion in those passages and cite the source inline in "
    "brackets by its number AND citation, e.g. [1; 15 U.S.C. § 1692c(b)] or "
    "[2; Heintz v. Jenkins, 514 U.S. 291]. Synthesize across multiple passages. "
    "If passages AGREE, note the agreement; if they CONFLICT or one limits/"
    "qualifies another, FLAG the conflict explicitly. If the passages do not "
    "fully cover the question, say so and do not speculate beyond them. Be "
    "precise and concise. This is general legal information, not legal advice."
)

_ANALYSIS_SYSTEM = (
    "You are a legal-research meta-analyzer. Given a question, the drafted answer, "
    "and the numbered source passages, respond with STRICT JSON only (no markdown, "
    "no code fences) of the form: "
    '{"conflicts": ["..."], "grounding": "...", "followups": ["...", "..."]}. '
    "conflicts = short notes where sources disagree or one qualifies another "
    "(empty list if all sources are consistent). "
    "grounding = ONE sentence on how well the passages support the answer "
    "(e.g. 'Well grounded — every claim maps to a cited passage' or 'Partial — "
    "the statute is on point but no case law was retrieved'). "
    "followups = 2-3 natural follow-up questions a researcher might ask next. "
    "Do not invent sources."
)


def _format_passages(hits: List[Dict[str, Any]]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        kind = "Opinion" if h.get("doc_type") == "opinion" else "Statute"
        court = f" ({h['court']}, {h['date']})" if h.get("court") else ""
        sect = f" [{h['legal_section']}]" if h.get("legal_section") and h.get("doc_type") == "opinion" else ""
        lines.append(
            f"[{i}] {kind}{sect}: {h['source_title']}{court}\n"
            f"    Citation: {h['citation']}\n"
            f"    Passage: {h['snippet']}"
        )
    return "\n\n".join(lines)


def _extract_json(raw: str) -> Dict[str, Any] | None:
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    if not fenced:
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = brace.group(0) if brace else candidate
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _extractive_answer(question: str, hits: List[Dict[str, Any]]) -> str:
    """Fallback when no LLM: return top passages verbatim, each cited."""
    parts = [
        "No LLM provider key is configured, so the following are the most "
        "relevant passages retrieved for your question (extractive mode):",
        "",
    ]
    for i, h in enumerate(hits, 1):
        kind = "opinion" if h.get("doc_type") == "opinion" else "statute"
        parts.append(f"{i}. [{h['citation']}] — {h['source_title']} ({kind})")
        parts.append(f"   {h['snippet']}")
        parts.append("")
    return "\n".join(parts).strip()


def _deterministic_followups(hits: List[Dict[str, Any]]) -> List[str]:
    fups: List[str] = []
    cites = [h["citation"] for h in hits[:2] if h.get("citation")]
    for c in cites:
        fups.append(f"What are the key exceptions or limits under {c}?")
    fups.append("Is there controlling case law interpreting this provision?")
    return fups[:3]


def answer(
    question: str,
    k: int = 5,
    collection_name: str = LEGAL_COLLECTION,
    deep: bool = True,
) -> Dict[str, Any]:
    """
    Phase 1 RAG pipeline:
      1. LLM query planner rewrites the question + identifies legal issues.
      2. If deep=True, fetch live CourtListener opinions and ingest them.
      3. Hybrid retrieval (dense + BM25 + RRF) over statutes + fetched case law.
      4. Citation-grounded synthesis + conflict detection + grounding +
         follow-ups (extractive fallback when no LLM key).

    Returns {answer, citations, rewritten_query, legal_issues, conflicts,
             followups, grounding, provider, retrieval, ingested}.
    """
    # 1. Plan the query.
    qplan = query_planner.plan(question)
    search_query = qplan["search_query"]
    legal_issues = qplan["legal_issues"]

    # 2. On-demand live case law (only for the SHARED legal collection).
    ingested_meta: List[Dict[str, Any]] = []
    if deep and collection_name == LEGAL_COLLECTION:
        for op in ingest_courtlistener(search_query):
            ingested_meta.append(
                {
                    "case_name": op.get("case_name", ""),
                    "citation": op.get("citation", ""),
                    "court": op.get("court", ""),
                    "date": op.get("date", ""),
                    "url": op.get("url", ""),
                }
            )

    # 3. Hybrid retrieval. Retrieve using the rewritten query (richer for sparse),
    # but keep the original question available for the LLM.
    retr_query = search_query or question
    hits, retrieval_debug = hybrid_retrieve(retr_query, k=k, collection_name=collection_name)

    if not hits:
        return {
            "answer": "No documents are indexed yet, so there is nothing to ground an answer on.",
            "citations": [],
            "rewritten_query": search_query,
            "legal_issues": legal_issues,
            "conflicts": [],
            "followups": [],
            "grounding": "No sources retrieved.",
            "provider": "none",
            "retrieval": retrieval_debug,
            "ingested": ingested_meta,
        }

    # 4. Synthesize.
    user_prompt = (
        f"Question: {question}\n\n"
        f"Passages:\n{_format_passages(hits)}\n\n"
        "Answer the question using only these passages, citing each one you rely "
        "on by [number; citation]. Note agreement and flag any conflict between sources."
    )
    text, provider = llm_router.synthesize(_SYSTEM_PROMPT, user_prompt)

    conflicts: List[str] = []
    grounding = ""
    followups: List[str] = []

    if text is None:
        text = _extractive_answer(question, hits)
        grounding = (
            f"Extractive mode (no LLM key): {len(hits)} passages retrieved via hybrid "
            f"dense+BM25 search; each statement above is a verbatim, cited passage."
        )
        followups = _deterministic_followups(hits)
    else:
        # Secondary structured pass for conflicts / grounding / followups.
        meta_prompt = (
            f"Question: {question}\n\nDrafted answer:\n{text}\n\n"
            f"Source passages:\n{_format_passages(hits)}"
        )
        meta_raw, _mp = llm_router.synthesize(_ANALYSIS_SYSTEM, meta_prompt)
        parsed = _extract_json(meta_raw) if meta_raw else None
        if parsed:
            c = parsed.get("conflicts") or []
            conflicts = [str(x).strip() for x in c if str(x).strip()] if isinstance(c, list) else []
            grounding = str(parsed.get("grounding") or "").strip()
            f = parsed.get("followups") or []
            followups = [str(x).strip() for x in f if str(x).strip()][:3] if isinstance(f, list) else []
        if not grounding:
            grounding = f"Grounded in {len(hits)} retrieved passages (hybrid dense+BM25+RRF)."
        if not followups:
            followups = _deterministic_followups(hits)

    return {
        "answer": text,
        "citations": hits,
        "rewritten_query": search_query,
        "legal_issues": legal_issues,
        "conflicts": conflicts,
        "followups": followups,
        "grounding": grounding,
        "provider": provider,
        "retrieval": retrieval_debug,
        "ingested": ingested_meta,
    }
