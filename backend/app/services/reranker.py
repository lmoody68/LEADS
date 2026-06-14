"""
Cross-encoder reranker (MasterBuildPlan §3.1 enhancement) for L.E.A.D.S.

After hybrid retrieval (dense + BM25 + RRF) produces a candidate pool, a
cross-encoder re-scores each (query, passage) pair JOINTLY — far more precise
than the bi-encoder embedding similarity used for first-stage recall — and we
keep the top-k. This is the standard retrieve-then-rerank pattern.

NO TORCH: uses FastEmbed's ONNX `TextCrossEncoder` (onnxruntime, the same
runtime the embedder already uses) so it adds no heavy deep-learning dependency.
Default model: ms-marco-MiniLM-L-6-v2 (small, CPU-friendly).

GRACEFUL: if fastembed/the model is unavailable (not installed, no network to
download the model, or RERANK_DISABLE=1), every call returns the original
ranking unchanged — reranking is a pure precision boost, never a hard
dependency. The model is loaded lazily once and cached for the process.
"""
from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict, List, Optional

_MODEL_NAME = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
_DISABLED = os.getenv("RERANK_DISABLE", "").strip().lower() in ("1", "true", "yes")

_encoder: Any = None
_load_failed = False


def _get_encoder():
    """Lazily load + cache the ONNX cross-encoder; None if unavailable."""
    global _encoder, _load_failed
    if _DISABLED or _load_failed:
        return None
    if _encoder is None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            _encoder = TextCrossEncoder(model_name=_MODEL_NAME)
            print(f"[reranker] cross-encoder ready: {_MODEL_NAME}")
        except Exception as exc:  # not installed / model download failed / etc.
            print(f"[reranker] unavailable ({exc}); retrieval will use RRF order.")
            _load_failed = True
            return None
    return _encoder


def warm_up() -> None:
    """
    Eagerly load the cross-encoder at startup so the FIRST user query doesn't
    pay the model load. Non-fatal — any failure just leaves reranking to load
    lazily / degrade to RRF order.
    """
    if _DISABLED:
        return
    try:
        _get_encoder()
    except Exception:
        pass


def available() -> bool:
    """
    Whether reranking can run — WITHOUT forcing a (slow) model load. Reports
    config intent + that fastembed is importable; the actual model loads lazily
    on first rerank().
    """
    if _DISABLED or _load_failed:
        return False
    if _encoder is not None:
        return True
    return importlib.util.find_spec("fastembed") is not None


def status() -> Dict[str, Any]:
    return {"available": available(), "model": _MODEL_NAME if not _DISABLED else None, "disabled": _DISABLED}


def rerank(
    query: str,
    hits: List[Dict[str, Any]],
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Re-score `hits` (each a dict with a 'snippet') against `query` with the
    cross-encoder and return them sorted best-first, annotating each with
    'rerank_score'. Returns the original order (optionally truncated to top_k)
    if the reranker is unavailable or errors. Never raises.
    """
    if not hits:
        return hits
    enc = _get_encoder()
    if enc is None:
        return hits[:top_k] if top_k else hits
    try:
        docs = [h.get("snippet", "") or "" for h in hits]
        scores = list(enc.rerank(query, docs))
        order = sorted(range(len(hits)), key=lambda i: scores[i], reverse=True)
        out: List[Dict[str, Any]] = []
        for i in order:
            h = dict(hits[i])
            h["rerank_score"] = round(float(scores[i]), 4)
            out.append(h)
        return out[:top_k] if top_k else out
    except Exception as exc:
        print(f"[reranker] rerank failed ({exc}); returning RRF order.")
        return hits[:top_k] if top_k else hits
