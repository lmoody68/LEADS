"""
Investigative Methodology Tutor (MasterBuildPlan §3.4) — Phase 4.

A BKT-powered adaptive tutor over the 5 L.E.A.D.S. curriculum modules
(OSINT Fundamentals · The Golden Search Strategy · Legal Research Methodology ·
Source Evaluation · Compliance & Ethics). The KCs and the Bayesian mastery
tracking live in `bkt.py` (ported from N.O.V.A.S.); this module is the content
layer that, using the existing free-first `llm_router`:

  * generate_lesson(kc)  — a focused lesson for one knowledge component
  * generate_quiz(kc)    — a mixed multiple-choice + short-answer quiz with a
                           grading rubric (held server-side; not sent to UI)
  * grade(kc, qid, ans)  — grade one answer, update BKT, give Socratic
                           remediation on a miss, and report mastery before→after
  * recommend the next KC by lowest mastery (delegated to bkt.recommend_next)

GUARDRAILS (consistent with the rest of L.E.A.D.S.):
  * EDUCATIONAL framing only — methodology, not a how-to for unlawful PII work.
  * The Compliance & Ethics module teaches lawful boundaries; it never produces
    step-by-step instructions for an unlawful method.
  * Stateless LLM calls (no training/retention). NO real people / NO real PII —
    examples are illustrative and generic.
  * DETERMINISTIC FALLBACK with no LLM key: a short canned lesson per KC and a
    canned multiple-choice quiz, so the tutor + BKT keep working with zero keys.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Dict, List, Optional

from . import bkt, llm_router

# Quiz state is held server-side keyed by question_id so the answer key + rubric
# never leave the backend (the UI only sees the prompt + options).
_QUIZZES: Dict[str, Dict[str, Any]] = {}
_quiz_lock = threading.Lock()


# ── Shared JSON extraction (mirrors compliance/rag — LLMs love code fences) ────
def _extract_json(raw: str) -> Optional[Any]:
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


# ── Curriculum view (modules + KCs, from the BKT engine) ──────────────────────
def get_curriculum() -> Dict[str, Any]:
    """Return the 5 modules and their KCs (no per-session state)."""
    modules = []
    for m in bkt.MODULE_ORDER:
        kcs = [
            {
                "kc_id": kc_id,
                "name": meta["name"],
                "description": meta["description"],
            }
            for kc_id, meta in bkt.KNOWLEDGE_COMPONENTS.items()
            if meta["module"] == m
        ]
        modules.append({"module": m, "kcs": kcs})
    return {
        "modules": modules,
        "total_kcs": len(bkt.KNOWLEDGE_COMPONENTS),
        "mastery_threshold": bkt.MASTERY_THRESHOLD,
    }


# ── LESSON ────────────────────────────────────────────────────────────────────
_LESSON_SYSTEM = (
    "You are the INVESTIGATIVE METHODOLOGY TUTOR of L.E.A.D.S., teaching OSINT and "
    "legal-research tradecraft to investigators, paralegals, and analysts. You teach "
    "METHODOLOGY only — never a how-to for unlawful PII gathering, pretexting, or "
    "accessing protected records. The Compliance module teaches lawful boundaries. "
    "Use NO real people and NO real personal data in examples; keep examples generic.\n\n"
    "Write a focused, practical lesson for the ONE knowledge component given. "
    "Respond with STRICT JSON ONLY (no markdown fences, no prose outside the JSON) "
    "of exactly this shape:\n"
    "{\n"
    '  "summary": "2-3 sentence plain-English overview of the concept",\n'
    '  "key_points": ["concrete teachable point", "..."],\n'
    '  "worked_example": "a short, generic illustrative example (no real names/PII)",\n'
    '  "pitfalls": ["a common mistake and how to avoid it", "..."],\n'
    '  "takeaway": "one-sentence memorable takeaway"\n'
    "}"
)


def _lesson_fallback(kc_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "summary": meta["description"],
        "key_points": [
            f"{meta['name']} is part of the '{meta['module']}' module.",
            "Apply it methodically and document your reasoning at each step.",
            "Always confirm findings against independent sources before relying on them.",
        ],
        "worked_example": (
            "Generic example: given a single starting fact, list what it lets you "
            "confirm, what it only suggests, and which independent source could "
            "corroborate it — without using any real person's data."
        ),
        "pitfalls": [
            "Treating a single source as proof — corroborate first.",
            "Skipping the lawful-purpose check before collecting protected information.",
        ],
        "takeaway": f"Master {meta['name']} by being systematic, skeptical, and lawful.",
    }


def generate_lesson(kc_id: str) -> Dict[str, Any]:
    meta = bkt.kc_meta(kc_id)
    if not meta:
        return {"error": f"Unknown KC: {kc_id}"}
    user = (
        f"Knowledge component: {meta['name']} (module: {meta['module']}).\n"
        f"Objective: {meta['description']}\n\n"
        "Write the lesson as STRICT JSON in the required shape."
    )
    raw, provider = llm_router.synthesize(_LESSON_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None
    if not isinstance(parsed, dict):
        out = _lesson_fallback(kc_id, meta)
        provider = "extractive (no LLM key)"
    else:
        out = {
            "summary": str(parsed.get("summary", "")).strip() or meta["description"],
            "key_points": _as_list(parsed.get("key_points")),
            "worked_example": str(parsed.get("worked_example", "")).strip(),
            "pitfalls": _as_list(parsed.get("pitfalls")),
            "takeaway": str(parsed.get("takeaway", "")).strip(),
        }
        if not out["key_points"]:
            out = _lesson_fallback(kc_id, meta)
    out.update(
        {
            "kc_id": kc_id,
            "kc_name": meta["name"],
            "module": meta["module"],
            "provider": provider,
        }
    )
    return out


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


# ── QUIZ ──────────────────────────────────────────────────────────────────────
_QUIZ_SYSTEM = (
    "You are the INVESTIGATIVE METHODOLOGY TUTOR of L.E.A.D.S. Write a short quiz "
    "for the ONE knowledge component given, to ASSESS mastery for Bayesian Knowledge "
    "Tracing. Teach methodology only; use NO real people / NO real PII. The quiz must "
    "mix question types.\n\n"
    "Respond with STRICT JSON ONLY (no markdown fences, no prose outside the JSON):\n"
    "{\n"
    '  "questions": [\n'
    '    {"type": "mc", "prompt": "question text", '
    '"options": ["A ...", "B ...", "C ...", "D ..."], '
    '"correct_index": 0, "explanation": "why the correct option is right"},\n'
    '    {"type": "short", "prompt": "question text", '
    '"rubric": ["key idea the answer MUST contain", "another key idea"], '
    '"model_answer": "a concise correct answer"}\n'
    "  ]\n"
    "}\n"
    "Include 2 'mc' and 1 'short' question. Keep options unambiguous; exactly one "
    "correct option per mc. rubric items are the concepts a passing short answer "
    "must mention."
)


def _quiz_fallback(kc_id: str, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "type": "mc",
            "prompt": f"Which best describes the goal of '{meta['name']}'?",
            "options": [
                meta["description"],
                "Collecting as much personal data as possible regardless of the law.",
                "Trusting the first source you find without checking it.",
                "Skipping documentation to work faster.",
            ],
            "correct_index": 0,
            "explanation": f"{meta['name']}: {meta['description']}",
        },
        {
            "type": "mc",
            "prompt": (
                "Before relying on a single fact you found, the disciplined next step is to:"
            ),
            "options": [
                "Corroborate it against at least one INDEPENDENT source.",
                "Publish it immediately.",
                "Assume it is true because it appeared in a search result.",
                "Discard all other leads.",
            ],
            "correct_index": 0,
            "explanation": "Triangulation against independent sources guards against error and disinformation.",
        },
    ]


def generate_quiz(kc_id: str) -> Dict[str, Any]:
    meta = bkt.kc_meta(kc_id)
    if not meta:
        return {"error": f"Unknown KC: {kc_id}"}

    user = (
        f"Knowledge component: {meta['name']} (module: {meta['module']}).\n"
        f"Objective: {meta['description']}\n\n"
        "Write the quiz as STRICT JSON in the required shape (2 mc + 1 short)."
    )
    raw, provider = llm_router.synthesize(_QUIZ_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None
    questions: List[Dict[str, Any]] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
        questions = [q for q in parsed["questions"] if isinstance(q, dict)]
    if not questions:
        questions = _quiz_fallback(kc_id, meta)
        provider = "extractive (no LLM key)"

    # Build the client-safe payload (no answer keys / rubric) and store the full
    # question (with answers) server-side keyed by question_id.
    client_questions: List[Dict[str, Any]] = []
    for q in questions:
        qid = uuid.uuid4().hex
        qtype = "short" if str(q.get("type", "mc")).lower().startswith("s") else "mc"
        if qtype == "mc":
            opts = _as_list(q.get("options"))[:6]
            if len(opts) < 2:
                continue
            try:
                correct_index = int(q.get("correct_index", 0))
            except Exception:
                correct_index = 0
            correct_index = max(0, min(correct_index, len(opts) - 1))
            full = {
                "qid": qid,
                "kc_id": kc_id,
                "type": "mc",
                "prompt": str(q.get("prompt", "")).strip(),
                "options": opts,
                "correct_index": correct_index,
                "explanation": str(q.get("explanation", "")).strip(),
            }
            client_questions.append(
                {"question_id": qid, "type": "mc", "prompt": full["prompt"], "options": opts}
            )
        else:
            full = {
                "qid": qid,
                "kc_id": kc_id,
                "type": "short",
                "prompt": str(q.get("prompt", "")).strip(),
                "rubric": _as_list(q.get("rubric")),
                "model_answer": str(q.get("model_answer", "")).strip(),
            }
            client_questions.append(
                {"question_id": qid, "type": "short", "prompt": full["prompt"]}
            )
        with _quiz_lock:
            _QUIZZES[qid] = full

    return {
        "kc_id": kc_id,
        "kc_name": meta["name"],
        "module": meta["module"],
        "questions": client_questions,
        "provider": provider,
    }


# ── GRADE + BKT update + Socratic remediation ─────────────────────────────────
_REMEDIATION_SYSTEM = (
    "You are the INVESTIGATIVE METHODOLOGY TUTOR of L.E.A.D.S. A learner answered a "
    "practice question INCORRECTLY. Give brief SOCRATIC remediation: a short hint and "
    "1-2 guiding questions that lead them to the right understanding WITHOUT simply "
    "stating the full answer. Teach methodology only; no real PII. 2-4 sentences, plain text."
)


def _short_answer_correct(answer: str, full: Dict[str, Any]) -> bool:
    """
    Grade a short answer. Prefer the LLM rubric judge; fall back to a keyword
    overlap against the rubric so grading still works with no LLM key.
    """
    rubric = full.get("rubric") or []
    ans = (answer or "").strip()
    if not ans:
        return False

    providers = llm_router.available_providers()
    if providers and rubric:
        system = (
            "You are a strict but fair grader. Decide if the learner's short answer "
            "demonstrates the key ideas in the rubric. Respond with STRICT JSON ONLY: "
            '{"correct": true|false, "reason": "one sentence"}'
        )
        user = (
            f"Question: {full.get('prompt','')}\n"
            f"Rubric (key ideas the answer must convey): {json.dumps(rubric)}\n"
            f"Model answer: {full.get('model_answer','')}\n"
            f"Learner answer: {ans}\n\n"
            "Mark correct only if the learner's answer conveys the rubric's key ideas "
            "(wording may differ). Return the JSON."
        )
        raw, _prov = llm_router.synthesize(system, user)
        parsed = _extract_json(raw) if raw else None
        if isinstance(parsed, dict) and "correct" in parsed:
            return bool(parsed["correct"])

    # Deterministic fallback: rubric keyword overlap.
    low = ans.lower()
    if not rubric:
        return len(low.split()) >= 5  # non-trivial attempt
    hits = 0
    for item in rubric:
        words = [w for w in re.findall(r"[a-z]{4,}", str(item).lower())]
        if words and any(w in low for w in words):
            hits += 1
    return hits >= max(1, (len(rubric) + 1) // 2)


def grade(session_id: str, kc_id: str, question_id: str, answer: Any) -> Dict[str, Any]:
    with _quiz_lock:
        full = _QUIZZES.get(question_id)
    if not full:
        return {"error": "unknown or expired question_id"}
    if full.get("kc_id") != kc_id:
        return {"error": "kc_id does not match this question"}

    correct = False
    feedback = ""
    if full["type"] == "mc":
        try:
            chosen = int(answer)
        except Exception:
            chosen = -1
        correct = chosen == full["correct_index"]
        if correct:
            feedback = full.get("explanation", "Correct.")
        else:
            right = full["options"][full["correct_index"]]
            feedback = (
                f"Not quite. The correct choice is: {right}. "
                f"{full.get('explanation', '')}".strip()
            )
    else:
        correct = _short_answer_correct(str(answer or ""), full)
        if correct:
            feedback = "Good — your answer covers the key ideas. " + (
                full.get("model_answer", "")
            )
        else:
            feedback = _socratic_remediation(full, str(answer or ""))

    # BKT update.
    update = bkt.observe(session_id, kc_id, correct)
    recommended = bkt.recommend_next(session_id)

    return {
        "kc_id": kc_id,
        "question_id": question_id,
        "type": full["type"],
        "correct": correct,
        "feedback": feedback,
        "mastery_before": update.get("mastery_before"),
        "mastery_after": update.get("mastery_after"),
        "level": update.get("level"),
        "color": update.get("color"),
        "mastered": update.get("mastered"),
        "recommended_next": recommended,
    }


def _socratic_remediation(full: Dict[str, Any], answer: str) -> str:
    providers = llm_router.available_providers()
    if providers:
        user = (
            f"Question: {full.get('prompt','')}\n"
            f"Key ideas a correct answer needs: {json.dumps(full.get('rubric') or [full.get('explanation','')])}\n"
            f"Learner's (incorrect) answer: {answer or '(left blank)'}\n\n"
            "Give short Socratic remediation as described."
        )
        raw, _prov = llm_router.synthesize(_REMEDIATION_SYSTEM, user)
        if raw and raw.strip():
            return raw.strip()
    # Fallback hint.
    rubric = full.get("rubric") or []
    hint = rubric[0] if rubric else full.get("explanation", "Revisit the lesson's key points.")
    return (
        "Not quite — let's reason it through. Consider: what would a disciplined "
        f"investigator check first here? Hint to focus on: {hint}"
    )
