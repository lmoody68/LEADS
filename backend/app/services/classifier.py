"""
Auxiliary Document Classifier — supervised-ML showcase for L.E.A.D.S.
(MasterBuildPlan §3 "auxiliary classifiers on public legal data").

Demonstrates the full supervised-ML loop on REAL legal data the app already
holds, reusing the existing embedding pipeline as features:

    MiniLM-L6 sentence embeddings (384-d, the SAME ONNX model the RAG uses)
        -> scikit-learn LogisticRegression head
        -> predicts a document's TYPE (statute / opinion / regulation / bill)

NO TORCH: features come from the already-computed Chroma embeddings (ONNX);
the head is classical sklearn. Trains in seconds on CPU.

This is an AUXILIARY METADATA tagger — it labels what KIND of legal document a
passage is. It is NOT a model that "knows the law," NOT legal advice, and is
never used to answer legal questions. Training data is the PUBLIC legal corpus
only (no PII). Metrics are HONEST: a stratified held-out test split + 5-fold
cross-validation (never training-set accuracy). Reproducible (fixed seed).

Classes with too few examples are EXCLUDED (and reported), so we never claim a
score on a class the model barely saw.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from . import rag

_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
_MODEL_PATH = _MODELS_DIR / "doctype_clf.joblib"
_META_PATH = _MODELS_DIR / "doctype_clf.json"

_MIN_PER_CLASS = 20  # don't train/score a class with fewer than this many samples
_RANDOM_STATE = 42

_model_cache: Any = None
_meta_cache: Optional[Dict[str, Any]] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _embed(texts: List[str]) -> np.ndarray:
    """Embed text with the SAME ONNX MiniLM model the corpus uses (no torch)."""
    return np.asarray(rag._EMBED_FN(texts))


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def _load_meta() -> Optional[Dict[str, Any]]:
    global _meta_cache
    if _meta_cache is not None:
        return _meta_cache
    if _META_PATH.exists():
        try:
            _meta_cache = json.loads(_META_PATH.read_text(encoding="utf-8"))
        except Exception:
            _meta_cache = None
    return _meta_cache


def status() -> Dict[str, Any]:
    meta = _load_meta()
    if not meta:
        return {"trained": False, "note": "No classifier trained yet — POST /api/classifier/train."}
    return {"trained": True, **meta}


def available() -> bool:
    return _MODEL_PATH.exists() or _model_cache is not None


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------
def train(label_field: str = "doc_type", min_per_class: int = _MIN_PER_CLASS) -> Dict[str, Any]:
    """
    Train the auxiliary classifier on the public corpus's embeddings + labels.
    Returns honest metrics (held-out test + 5-fold CV) or {error}.
    """
    global _model_cache, _meta_cache

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            confusion_matrix,
            f1_score,
        )
        from sklearn.model_selection import cross_val_score, train_test_split
        import joblib
    except Exception as exc:
        return {"error": f"scikit-learn/joblib not installed ({exc}). pip install scikit-learn joblib."}

    col = rag.get_collection()
    got = col.get(include=["embeddings", "metadatas"])
    X_all = np.asarray(got.get("embeddings"))
    metas = got.get("metadatas") or []
    if X_all.size == 0 or not metas:
        return {"error": "Corpus has no embeddings yet — ingest data first."}

    labels_all = [str((m or {}).get(label_field) or "").strip() for m in metas]
    counts = Counter(l for l in labels_all if l)
    keep = {l for l, c in counts.items() if c >= min_per_class}
    excluded = {l: c for l, c in counts.items() if l not in keep}
    if len(keep) < 2:
        return {
            "error": f"Need >=2 classes with >={min_per_class} samples for '{label_field}'. "
            f"Found: {dict(counts)}."
        }

    idx = [i for i, l in enumerate(labels_all) if l in keep]
    X = X_all[idx]
    y = np.array([labels_all[i] for i in idx])
    class_list = sorted(keep)

    # Honest evaluation: stratified held-out test split.
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=_RANDOM_STATE
    )
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=_RANDOM_STATE)
    clf.fit(X_tr, y_tr)
    y_pred = clf.predict(X_te)
    holdout_acc = round(float(accuracy_score(y_te, y_pred)), 4)
    holdout_macro_f1 = round(float(f1_score(y_te, y_pred, average="macro")), 4)
    report = classification_report(y_te, y_pred, labels=class_list, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_te, y_pred, labels=class_list).tolist()

    # 5-fold cross-validated macro-F1 for a robustness check.
    cv = cross_val_score(
        LogisticRegression(max_iter=2000, class_weight="balanced", random_state=_RANDOM_STATE),
        X, y, cv=5, scoring="f1_macro",
    )

    # Deploy model = refit on ALL kept samples.
    final = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=_RANDOM_STATE)
    final.fit(X, y)

    per_class = {
        c: {
            "precision": round(float(report[c]["precision"]), 3),
            "recall": round(float(report[c]["recall"]), 3),
            "f1": round(float(report[c]["f1-score"]), 3),
            "support": int(report[c]["support"]),
            "train_count": int(counts[c]),
        }
        for c in class_list
        if c in report
    }

    meta = {
        "model": "LogisticRegression head on MiniLM-L6 (384-d) sentence embeddings",
        "task": f"document {label_field} classification (auxiliary metadata tagger)",
        "label_field": label_field,
        "classes": class_list,
        "n_samples": int(len(y)),
        "n_features": int(X.shape[1]),
        "holdout": {"test_size": 0.2, "accuracy": holdout_acc, "macro_f1": holdout_macro_f1},
        "cross_val": {
            "folds": 5,
            "macro_f1_mean": round(float(cv.mean()), 4),
            "macro_f1_std": round(float(cv.std()), 4),
        },
        "per_class": per_class,
        "confusion": {"labels": class_list, "matrix": cm},
        "excluded_classes": excluded,
        "min_per_class": min_per_class,
        "trained_at": _now_iso(),
        "disclaimer": "Auxiliary document-TYPE tagger trained on public legal text. "
        "NOT legal advice and NOT a model of the law.",
    }

    try:
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(final, _MODEL_PATH)
        _META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception as exc:
        return {"error": f"trained but failed to persist: {exc}"}

    _model_cache = final
    _meta_cache = meta
    return meta


# ---------------------------------------------------------------------------
# Predict
# ---------------------------------------------------------------------------
def _load_model() -> Any:
    global _model_cache
    if _model_cache is None and _MODEL_PATH.exists():
        try:
            import joblib

            _model_cache = joblib.load(_MODEL_PATH)
        except Exception:
            _model_cache = None
    return _model_cache


def predict(text: str) -> Dict[str, Any]:
    """Classify a piece of legal text by document type. {error} if untrained."""
    text = (text or "").strip()
    if not text:
        return {"error": "text is required"}
    model = _load_model()
    if model is None:
        return {"error": "No classifier trained yet — POST /api/classifier/train first."}
    try:
        X = _embed([text])
        proba = model.predict_proba(X)[0]
        classes = list(model.classes_)
        order = np.argsort(proba)[::-1]
        ranked = [
            {"label": str(classes[i]), "confidence": round(float(proba[i]), 4)} for i in order
        ]
        return {
            "label": ranked[0]["label"],
            "confidence": ranked[0]["confidence"],
            "probabilities": ranked[:5],
            "model": "MiniLM-384 embeddings -> LogisticRegression",
            "disclaimer": "Auxiliary document-TYPE classification, not legal advice.",
        }
    except Exception as exc:
        return {"error": f"prediction failed: {exc}"}
