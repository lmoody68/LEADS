"""
Bayesian Knowledge Tracing (BKT) engine for L.E.A.D.S. — Phase 4.

PORTED FROM N.O.V.A.S. (`N.O.V.A.S/backend/services/knowledge_tracker.py`):
the per-knowledge-component latent-mastery model and the Bayesian posterior
update are taken directly from that implementation; only the knowledge
components (KCs) are re-authored for L.E.A.D.S.'s investigative/legal-research
curriculum (MasterBuildPlan §3.4). The BKT math is unchanged:

    P(known) per KC, with four classic BKT parameters:
      * p_init   = P(L0)        — prior probability the skill is already known
      * p_transit/p_learn        — probability of learning on a correct attempt
      * p_slip   = P(wrong|known)
      * p_guess  = P(correct|not-known)

    On each observation we apply the Bayesian posterior update:
      correct:   P' = (P·(1-slip)) / (P·(1-slip) + (1-P)·guess), then learn-gain
      incorrect: P' = (P·slip)     / (P·slip     + (1-P)·(1-guess)), then slip-loss

A KC is considered MASTERED at P(known) ≥ MASTERY_THRESHOLD (~0.95).

Session-keyed state: an `X-Session-Id` (header or body) keys an in-memory dict.
Optional JSON persistence to a gitignored dir (`bkt_state/`) lets a session's
mastery survive a restart. NOTHING here trains an LLM or stores PII — it is a
small probability vector per anonymous session id.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

# ── BKT parameters (classic four; values match N.O.V.A.S. behaviour) ──────────
# N.O.V.A.S. used P(correct|mastered)=0.9 and P(correct|not-mastered)=0.3, i.e.
# slip=0.1 and guess=0.3, plus a learning-gain on correct and a slip-loss on miss.
P_INIT_DEFAULT = 0.10        # P(L0) — prior mastery before any evidence
P_SLIP = 0.10               # P(incorrect | known)
P_GUESS = 0.30              # P(correct  | not-known)
P_LEARN = 0.10              # transit/learning gain applied on a correct attempt
SLIP_LOSS = 0.05            # small downward nudge applied on an incorrect attempt
MASTERY_THRESHOLD = 0.95    # P(known) at/above which a KC counts as mastered

# Convenience derived values (kept named for readability in the Bayes step).
_P_CORRECT_GIVEN_MASTERED = 1.0 - P_SLIP        # 0.9
_P_CORRECT_GIVEN_NOT_MASTERED = P_GUESS         # 0.3


# ── Knowledge Components — L.E.A.D.S. investigative-methodology curriculum ─────
# Grouped by the 5 modules from MasterBuildPlan §3.4. Each KC is a single
# learning objective the tutor + sandbox assess and the BKT tracks.
KNOWLEDGE_COMPONENTS: Dict[str, Dict[str, Any]] = {
    # 1. OSINT Fundamentals
    "osint.principles": {
        "name": "OSINT Principles",
        "module": "OSINT Fundamentals",
        "description": "Open-source intelligence definition, the intelligence cycle, and lawful collection boundaries.",
        "prior": P_INIT_DEFAULT,
    },
    "osint.source_taxonomy": {
        "name": "Source Taxonomy",
        "module": "OSINT Fundamentals",
        "description": "Classify sources: public records, media, social, technical, and human-derived open data.",
        "prior": P_INIT_DEFAULT,
    },
    "osint.search_operators": {
        "name": "Search Engine Operators",
        "module": "OSINT Fundamentals",
        "description": "Advanced operators (site:, filetype:, intitle:, quotes, boolean) for precise queries.",
        "prior": P_INIT_DEFAULT,
    },
    # 2. The Golden Search Strategy
    "golden.lead_development": {
        "name": "Lead Development",
        "module": "The Golden Search Strategy",
        "description": "Turn a single known identifier into new leads; expand and prioritize the search frontier.",
        "prior": P_INIT_DEFAULT,
    },
    "golden.triangulation": {
        "name": "Source Triangulation",
        "module": "The Golden Search Strategy",
        "description": "Confirm a fact with two-to-three INDEPENDENT sources before relying on it.",
        "prior": P_INIT_DEFAULT,
    },
    "golden.dead_end_recovery": {
        "name": "Dead-End Recovery",
        "module": "The Golden Search Strategy",
        "description": "Recognize a dead end and pivot: re-frame the query, change source type, or revisit assumptions.",
        "prior": P_INIT_DEFAULT,
    },
    # 3. Legal Research Methodology
    "legal.case_hierarchy": {
        "name": "Case Law Hierarchy",
        "module": "Legal Research Methodology",
        "description": "Binding vs. persuasive authority; court hierarchy and jurisdiction.",
        "prior": P_INIT_DEFAULT,
    },
    "legal.statutory_interpretation": {
        "name": "Statutory Interpretation",
        "module": "Legal Research Methodology",
        "description": "Read a statute: plain meaning, definitions, structure, and canons of construction.",
        "prior": P_INIT_DEFAULT,
    },
    "legal.shepardizing": {
        "name": "Shepardizing & Citators",
        "module": "Legal Research Methodology",
        "description": "Verify a case is still good law — overruled, distinguished, followed, or superseded.",
        "prior": P_INIT_DEFAULT,
    },
    # 4. Source Evaluation
    "eval.primary_secondary": {
        "name": "Primary vs. Secondary",
        "module": "Source Evaluation",
        "description": "Distinguish primary authority (courts, legislatures) from secondary commentary.",
        "prior": P_INIT_DEFAULT,
    },
    "eval.bias_detection": {
        "name": "Bias & Interest Detection",
        "module": "Source Evaluation",
        "description": "Identify a source's stake, funding, or slant that may color its claims.",
        "prior": P_INIT_DEFAULT,
    },
    "eval.credibility": {
        "name": "Credibility Assessment",
        "module": "Source Evaluation",
        "description": "Weigh authority, currency, corroboration, bias, and completeness to rate a source.",
        "prior": P_INIT_DEFAULT,
    },
    # 5. Compliance & Ethics
    "compliance.permissible_purpose": {
        "name": "Permissible Purpose",
        "module": "Compliance & Ethics",
        "description": "When the law (FCRA/DPPA/GLBA) permits obtaining or using protected information.",
        "prior": P_INIT_DEFAULT,
    },
    "compliance.privacy_boundaries": {
        "name": "Privacy Boundaries",
        "module": "Compliance & Ethics",
        "description": "Where lawful collection ends: PII, protected records, pretexting, and harassment.",
        "prior": P_INIT_DEFAULT,
    },
    "compliance.lawful_skiptrace": {
        "name": "Lawful Skip Tracing",
        "module": "Compliance & Ethics",
        "description": "When and how locating a person is lawful vs. unlawful under FDCPA/DPPA/GLBA.",
        "prior": P_INIT_DEFAULT,
    },
}

# Module display order for grouping in the UI.
MODULE_ORDER: List[str] = [
    "OSINT Fundamentals",
    "The Golden Search Strategy",
    "Legal Research Methodology",
    "Source Evaluation",
    "Compliance & Ethics",
]


# ── State store (in-memory + optional JSON persistence) ───────────────────────
_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

# Gitignored persistence dir (see .gitignore addition for bkt_state/).
_STATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bkt_state"
)
_PERSIST = os.getenv("BKT_PERSIST", "1") not in ("0", "false", "False", "")


def _state_path(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))[:80] or "anon"
    return os.path.join(_STATE_DIR, f"{safe}.json")


def _fresh_session() -> Dict[str, Any]:
    return {
        kc_id: {
            "p_mastery": kc["prior"],
            "attempts": 0,
            "correct": 0,
            "incorrect": 0,
            "history": [],  # list of bool
        }
        for kc_id, kc in KNOWLEDGE_COMPONENTS.items()
    }


def _persist_session(session_id: str, session: Dict[str, Any]) -> None:
    if not _PERSIST:
        return
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_state_path(session_id), "w", encoding="utf-8") as f:
            json.dump({"session_id": session_id, "kcs": session}, f)
    except Exception:
        # Persistence is best-effort; never break a request over disk I/O.
        pass


def _load_persisted(session_id: str) -> Optional[Dict[str, Any]]:
    if not _PERSIST:
        return None
    path = _state_path(session_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        saved = data.get("kcs", {})
        fresh = _fresh_session()
        for kc_id, st in saved.items():
            if kc_id in fresh and isinstance(st, dict):
                fresh[kc_id]["p_mastery"] = float(st.get("p_mastery", P_INIT_DEFAULT))
                fresh[kc_id]["attempts"] = int(st.get("attempts", 0))
                fresh[kc_id]["correct"] = int(st.get("correct", 0))
                fresh[kc_id]["incorrect"] = int(st.get("incorrect", 0))
                fresh[kc_id]["history"] = list(st.get("history", []))[-50:]
        return fresh
    except Exception:
        return None


def _get_or_init_session(session_id: str) -> Dict[str, Any]:
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = _load_persisted(session_id) or _fresh_session()
        return _sessions[session_id]


# ── Core BKT update (ported math) ─────────────────────────────────────────────
def _bkt_update(p: float, is_correct: bool) -> float:
    """One Bayesian Knowledge Tracing observation update. Returns new P(known)."""
    if is_correct:
        numerator = _P_CORRECT_GIVEN_MASTERED * p
        denominator = (
            _P_CORRECT_GIVEN_MASTERED * p
            + _P_CORRECT_GIVEN_NOT_MASTERED * (1.0 - p)
        )
        updated = numerator / denominator if denominator > 0 else p
        # Learning gain (p_transit): some probability the attempt itself taught it.
        updated = updated + (1.0 - updated) * P_LEARN
    else:
        p_incorrect_given_mastered = 1.0 - _P_CORRECT_GIVEN_MASTERED       # slip
        p_incorrect_given_not_mastered = 1.0 - _P_CORRECT_GIVEN_NOT_MASTERED  # 1-guess
        numerator = p_incorrect_given_mastered * p
        denominator = (
            p_incorrect_given_mastered * p
            + p_incorrect_given_not_mastered * (1.0 - p)
        )
        updated = numerator / denominator if denominator > 0 else p
        updated = max(0.0, updated - SLIP_LOSS)
    return min(1.0, max(0.0, updated))


def _mastery_level(p: float) -> str:
    """Qualitative band → drives the red/yellow/green dashboard."""
    if p >= MASTERY_THRESHOLD:
        return "mastered"      # green
    if p >= 0.6:
        return "developing"    # green-ish / nearly there
    if p >= 0.3:
        return "learning"      # yellow
    return "not_started"       # red


def _rag_color(p: float) -> str:
    """Red / yellow / green band (N.O.R.M.A.-style readiness)."""
    if p >= 0.75:
        return "green"
    if p >= 0.4:
        return "yellow"
    return "red"


# ── Public helpers ────────────────────────────────────────────────────────────
def observe(session_id: str, kc_id: str, is_correct: bool) -> Dict[str, Any]:
    """
    Record one correct/incorrect observation for a KC; run the BKT update.
    Returns {kc_id, name, module, mastery_before, mastery_after, level, color, ...}.
    """
    if kc_id not in KNOWLEDGE_COMPONENTS:
        return {"error": f"Unknown KC: {kc_id}"}

    session = _get_or_init_session(session_id)
    with _lock:
        state = session[kc_id]
        old_p = state["p_mastery"]
        new_p = _bkt_update(old_p, is_correct)
        state["p_mastery"] = new_p
        state["attempts"] += 1
        state["correct" if is_correct else "incorrect"] += 1
        state["history"].append(bool(is_correct))
    _persist_session(session_id, session)

    meta = KNOWLEDGE_COMPONENTS[kc_id]
    return {
        "kc_id": kc_id,
        "name": meta["name"],
        "module": meta["module"],
        "mastery_before": round(old_p, 4),
        "mastery_after": round(new_p, 4),
        "level": _mastery_level(new_p),
        "color": _rag_color(new_p),
        "mastered": new_p >= MASTERY_THRESHOLD,
        "improved": new_p > old_p,
        "attempts": state["attempts"],
        "correct": state["correct"],
        "incorrect": state["incorrect"],
    }


def _kc_view(kc_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    meta = KNOWLEDGE_COMPONENTS.get(kc_id, {})
    p = state["p_mastery"]
    return {
        "kc_id": kc_id,
        "name": meta.get("name", kc_id),
        "module": meta.get("module", ""),
        "description": meta.get("description", ""),
        "p_mastery": round(p, 4),
        "level": _mastery_level(p),
        "color": _rag_color(p),
        "mastered": p >= MASTERY_THRESHOLD,
        "attempts": state["attempts"],
        "correct": state["correct"],
        "incorrect": state["incorrect"],
    }


def get_profile(session_id: str) -> Dict[str, Any]:
    """
    Full per-session mastery profile, grouped by module + an overall readiness %.
    Drives the red/yellow/green mastery dashboard.
    """
    session = _get_or_init_session(session_id)
    by_module: Dict[str, List[Dict[str, Any]]] = {m: [] for m in MODULE_ORDER}
    all_views: List[Dict[str, Any]] = []
    for kc_id in KNOWLEDGE_COMPONENTS:
        view = _kc_view(kc_id, session[kc_id])
        all_views.append(view)
        by_module.setdefault(view["module"], []).append(view)

    modules = []
    for m in MODULE_ORDER:
        kcs = by_module.get(m, [])
        avg = sum(k["p_mastery"] for k in kcs) / len(kcs) if kcs else 0.0
        modules.append(
            {
                "module": m,
                "avg_mastery": round(avg, 4),
                "color": _rag_color(avg),
                "mastered_count": sum(1 for k in kcs if k["mastered"]),
                "kc_count": len(kcs),
                "kcs": kcs,
            }
        )

    overall = (
        sum(v["p_mastery"] for v in all_views) / len(all_views) if all_views else 0.0
    )
    return {
        "session_id": session_id,
        "overall_readiness_percent": round(overall * 100, 1),
        "overall_color": _rag_color(overall),
        "mastered_kcs": sum(1 for v in all_views if v["mastered"]),
        "total_kcs": len(all_views),
        "total_attempts": sum(v["attempts"] for v in all_views),
        "mastery_threshold": MASTERY_THRESHOLD,
        "modules": modules,
    }


def recommend_next(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Recommend the next KC to study = the non-mastered KC with the LOWEST P(known)
    (ties broken by fewest attempts). Returns None if everything is mastered.
    """
    session = _get_or_init_session(session_id)
    candidates = [
        _kc_view(kc_id, st)
        for kc_id, st in session.items()
        if st["p_mastery"] < MASTERY_THRESHOLD
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda v: (v["p_mastery"], v["attempts"]))
    return candidates[0]


def kc_meta(kc_id: str) -> Optional[Dict[str, Any]]:
    return KNOWLEDGE_COMPONENTS.get(kc_id)
