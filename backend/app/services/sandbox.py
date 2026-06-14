"""
Practice Sandbox (MasterBuildPlan §3.6) — Phase 4.

Generates a CLEARLY-SYNTHETIC, FICTIONAL investigative scenario so a learner can
practice the "Golden Search Strategy" without touching any real person or real
PII. The learner submits their research APPROACH (methodology), and the LLM
evaluates it — did they triangulate? assess source credibility? respect
permissible-purpose / compliance? handle dead-ends? — producing a score +
feedback. BKT then updates the relevant skill KCs.

GUARDRAILS (non-negotiable, baked into the prompts + post-processing):
  * SYNTHETIC ONLY. Every name, record, filing, and address in a generated
    scenario is FICTIONAL and explicitly LABELED synthetic. The generator is
    instructed NEVER to produce real personal data, and the result is tagged
    `synthetic: true` with a visible banner string.
  * The evaluator rewards LAWFUL methodology and flags any unlawful step (e.g.
    pretexting, buying DMV data); it never coaches an unlawful method.
  * Stateless LLM calls; nothing trains/retains. Reuses the existing free-first
    `llm_router`.
  * DETERMINISTIC FALLBACK with no LLM key: a hand-written synthetic scenario and
    a keyword-based methodology rubric so the sandbox + BKT keep working.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Dict, List, Optional

from . import bkt, llm_router

_SCENARIOS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

SYNTHETIC_BANNER = (
    "⚠ SYNTHETIC TRAINING SCENARIO — every name, record, and filing below is "
    "FICTIONAL and AI-generated for practice only. No real person or real data is "
    "involved."
)

# KCs this exercise assesses (the Golden-Search + evaluation + compliance skills).
_SANDBOX_KCS = [
    "golden.lead_development",
    "golden.triangulation",
    "golden.dead_end_recovery",
    "eval.credibility",
    "compliance.permissible_purpose",
]


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


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


# ── SCENARIO GENERATION ───────────────────────────────────────────────────────
_SCENARIO_SYSTEM = (
    "You are the PRACTICE SANDBOX of L.E.A.D.S., a TRAINING tool for investigative "
    "methodology. Generate a SHORT, CLEARLY FICTIONAL skip-trace / locate scenario "
    "for a learner to practice the 'Golden Search Strategy'.\n\n"
    "ABSOLUTE RULES — non-negotiable:\n"
    "- EVERYTHING is SYNTHETIC and FICTIONAL. Invent fake names, fake addresses, "
    "fake case numbers, fake employers, fake news outlets. NEVER use a real person, "
    "real address, real phone number, or any real personal data.\n"
    "- Use obviously-fictional markers (e.g. names like 'Jordan Vale', towns like "
    "'Maple Hollow', outlets like 'The Fictional Courier'). Do NOT use real public "
    "figures.\n"
    "- This teaches LAWFUL methodology. The scenario's legitimate purpose must be a "
    "LAWFUL one (e.g. serving process, a debt within FDCPA/FCRA bounds, witness "
    "location for litigation). Do not frame the goal as harassment, stalking, or "
    "obtaining protected DMV/credit data unlawfully.\n\n"
    "Respond with STRICT JSON ONLY (no markdown fences, no prose outside the JSON):\n"
    "{\n"
    '  "title": "short scenario title",\n'
    '  "objective": "the LAWFUL locate/research goal, 1-2 sentences",\n'
    '  "lawful_purpose": "the permissible purpose that makes this lawful",\n'
    '  "known_facts": ["fictional starting fact", "..."],\n'
    '  "available_sources": [{"name": "fictional source", "type": "public record|news|filing|directory", "reliability": "high|medium|low", "note": "what it offers and any catch"}],\n'
    '  "red_herrings": ["a misleading lead or dead-end to watch for", "..."],\n'
    '  "ideal_approach": ["step a strong methodology would take", "..."]\n'
    "}\n"
    "Make exactly ONE source a tempting-but-unreliable trap, and include at least one "
    "dead-end. Keep it concise."
)


def _scenario_fallback() -> Dict[str, Any]:
    return {
        "title": "Locating a Witness for Civil Litigation",
        "objective": (
            "Locate fictional witness 'Jordan Vale' to serve a subpoena for an "
            "ongoing civil case in the fictional town of Maple Hollow."
        ),
        "lawful_purpose": "Service of process / witness location for active litigation.",
        "known_facts": [
            "Last known employer (2 years ago): 'Hollow Brook Logistics' (fictional).",
            "A fictional 2021 civil filing lists a P.O. box in Maple Hollow.",
            "A relative, 'Casey Vale', is listed in a fictional business directory.",
        ],
        "available_sources": [
            {
                "name": "Maple Hollow County court records (fictional)",
                "type": "public record",
                "reliability": "high",
                "note": "Primary filings; reliable but may be stale.",
            },
            {
                "name": "QuickFindPeople.example (fictional aggregator)",
                "type": "directory",
                "reliability": "low",
                "note": "Tempting one-click 'current address' — but unverified and often wrong (trap).",
            },
            {
                "name": "The Fictional Courier archive",
                "type": "news",
                "reliability": "medium",
                "note": "May mention the employer; corroborate before relying on it.",
            },
        ],
        "red_herrings": [
            "A same-name 'Jordan Vale' in a different state — verify identity before pursuing.",
            "The low-reliability aggregator's 'current address' is a dead-end if taken at face value.",
        ],
        "ideal_approach": [
            "Confirm the lawful purpose (service of process) before collecting anything.",
            "Start from primary records (court filings), not the aggregator.",
            "Triangulate the employer across the news archive AND a filing before relying on it.",
            "Disambiguate the same-name witness using the case context.",
            "Treat the aggregator as a lead to verify, never as proof; recover from the dead-end by pivoting to the relative listing.",
        ],
    }


def generate_scenario() -> Dict[str, Any]:
    raw, provider = llm_router.synthesize(
        _SCENARIO_SYSTEM,
        "Generate one fictional practice scenario now as STRICT JSON in the required shape.",
    )
    parsed = _extract_json(raw) if raw else None
    if not isinstance(parsed, dict) or not parsed.get("objective"):
        scenario = _scenario_fallback()
        provider = "extractive (no LLM key)"
    else:
        sources = []
        for s in parsed.get("available_sources") or []:
            if isinstance(s, dict):
                sources.append(
                    {
                        "name": str(s.get("name", "")).strip(),
                        "type": str(s.get("type", "")).strip(),
                        "reliability": str(s.get("reliability", "")).strip(),
                        "note": str(s.get("note", "")).strip(),
                    }
                )
        scenario = {
            "title": str(parsed.get("title", "Practice Scenario")).strip(),
            "objective": str(parsed.get("objective", "")).strip(),
            "lawful_purpose": str(parsed.get("lawful_purpose", "")).strip(),
            "known_facts": _as_list(parsed.get("known_facts")),
            "available_sources": sources,
            "red_herrings": _as_list(parsed.get("red_herrings")),
            "ideal_approach": _as_list(parsed.get("ideal_approach")),
        }
        if not scenario["known_facts"] or not scenario["available_sources"]:
            scenario = _scenario_fallback()
            provider = "extractive (no LLM key)"

    scenario_id = uuid.uuid4().hex
    # Store the full scenario (incl. ideal_approach answer key) server-side.
    with _lock:
        _SCENARIOS[scenario_id] = scenario

    # Client payload: hide the ideal_approach (the answer key) until after eval.
    return {
        "scenario_id": scenario_id,
        "synthetic": True,
        "synthetic_banner": SYNTHETIC_BANNER,
        "title": scenario["title"],
        "objective": scenario["objective"],
        "lawful_purpose": scenario["lawful_purpose"],
        "known_facts": scenario["known_facts"],
        "available_sources": scenario["available_sources"],
        "assessed_kcs": [
            {"kc_id": k, "name": bkt.KNOWLEDGE_COMPONENTS[k]["name"]} for k in _SANDBOX_KCS
        ],
        "provider": provider,
    }


# ── METHODOLOGY EVALUATION ────────────────────────────────────────────────────
_EVAL_SYSTEM = (
    "You are the PRACTICE SANDBOX EVALUATOR of L.E.A.D.S. A learner submitted their "
    "research APPROACH to a FICTIONAL practice scenario. Evaluate the METHODOLOGY "
    "(not whether they 'found' anyone). Reward lawful, rigorous tradecraft and flag "
    "weaknesses. Be specific and constructive. Teach lawful methodology only — if the "
    "learner proposed an unlawful step, flag it and give the lawful alternative.\n\n"
    "Score each dimension 0-100:\n"
    "- triangulation: did they corroborate facts across INDEPENDENT sources?\n"
    "- source_credibility: did they weigh reliability and resist the unreliable trap?\n"
    "- compliance: did they confirm a lawful/permissible purpose and stay within it?\n"
    "- dead_end_handling: did they recognize and recover from dead-ends / red herrings?\n"
    "- lead_development: did they expand leads systematically from the known facts?\n\n"
    "Respond with STRICT JSON ONLY (no markdown fences):\n"
    "{\n"
    '  "scores": {"triangulation": 0-100, "source_credibility": 0-100, '
    '"compliance": 0-100, "dead_end_handling": 0-100, "lead_development": 0-100},\n'
    '  "overall": 0-100,\n'
    '  "did_well": ["specific strength", "..."],\n'
    '  "could_improve": ["specific, actionable improvement", "..."],\n'
    '  "compliance_flags": ["any unlawful or risky step + the lawful alternative", "..."],\n'
    '  "verdict": "pass" | "needs_work"\n'
    "}"
)

# Map the evaluator's score dimensions → BKT KCs.
_DIM_TO_KC = {
    "triangulation": "golden.triangulation",
    "source_credibility": "eval.credibility",
    "compliance": "compliance.permissible_purpose",
    "dead_end_handling": "golden.dead_end_recovery",
    "lead_development": "golden.lead_development",
}
_PASS_DIM = 60  # a dimension score ≥ this counts as a 'correct' BKT observation


def _eval_fallback(scenario: Dict[str, Any], approach: str) -> Dict[str, Any]:
    low = (approach or "").lower()

    def has(*words: str) -> bool:
        return any(w in low for w in words)

    scores = {
        "triangulation": 75 if has("triangulat", "corroborat", "independent", "cross-ref", "cross ref", "confirm") else 35,
        "source_credibility": 75 if has("reliab", "credib", "primary source", "unreliable", "verify", "aggregator", "trap") else 35,
        "compliance": 75 if has("lawful", "permissible", "purpose", "fdcpa", "fcra", "dppa", "subpoena", "service of process") else 30,
        "dead_end_handling": 70 if has("dead end", "dead-end", "pivot", "red herring", "same name", "same-name", "disambiguat") else 35,
        "lead_development": 70 if has("lead", "expand", "start", "relative", "employer", "filing", "record") else 40,
    }
    overall = round(sum(scores.values()) / len(scores))
    did_well = [f"{k.replace('_',' ').title()} addressed." for k, v in scores.items() if v >= _PASS_DIM]
    improve = [f"Strengthen {k.replace('_',' ')}." for k, v in scores.items() if v < _PASS_DIM]
    flags = []
    if has("dmv", "pretext", "pose as", "buy data", "hack"):
        flags.append(
            "Approach hints at an unlawful method (e.g. DMV/pretexting). Use only "
            "lawful channels tied to the permissible purpose (e.g. subpoena, public records)."
        )
    return {
        "scores": scores,
        "overall": overall,
        "did_well": did_well or ["You submitted an approach to evaluate."],
        "could_improve": improve or ["Add explicit triangulation and a lawful-purpose check."],
        "compliance_flags": flags,
        "verdict": "pass" if overall >= _PASS_DIM else "needs_work",
        "provider": "extractive (no LLM key)",
    }


def evaluate(session_id: str, scenario_id: str, approach: str) -> Dict[str, Any]:
    with _lock:
        scenario = _SCENARIOS.get(scenario_id)
    if not scenario:
        return {"error": "unknown or expired scenario_id"}
    approach = (approach or "").strip()
    if not approach:
        return {"error": "approach is required"}

    user = (
        f"SCENARIO (fictional):\nObjective: {scenario.get('objective','')}\n"
        f"Lawful purpose: {scenario.get('lawful_purpose','')}\n"
        f"Known facts: {json.dumps(scenario.get('known_facts', []))}\n"
        f"Available sources: {json.dumps(scenario.get('available_sources', []))}\n"
        f"(Reference) strong approach: {json.dumps(scenario.get('ideal_approach', []))}\n\n"
        f"LEARNER'S SUBMITTED APPROACH:\n{approach}\n\n"
        "Evaluate the methodology as STRICT JSON in the required shape."
    )
    raw, provider = llm_router.synthesize(_EVAL_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None

    if not isinstance(parsed, dict) or not isinstance(parsed.get("scores"), dict):
        result = _eval_fallback(scenario, approach)
    else:
        scores_in = parsed.get("scores") or {}
        scores: Dict[str, int] = {}
        for dim in _DIM_TO_KC:
            try:
                scores[dim] = max(0, min(100, int(round(float(scores_in.get(dim, 0))))))
            except Exception:
                scores[dim] = 0
        try:
            overall = int(round(float(parsed.get("overall", sum(scores.values()) / len(scores)))))
        except Exception:
            overall = round(sum(scores.values()) / len(scores))
        result = {
            "scores": scores,
            "overall": max(0, min(100, overall)),
            "did_well": _as_list(parsed.get("did_well")),
            "could_improve": _as_list(parsed.get("could_improve")),
            "compliance_flags": _as_list(parsed.get("compliance_flags")),
            "verdict": "pass" if str(parsed.get("verdict", "")).lower().startswith("pass") else "needs_work",
            "provider": provider,
        }

    # BKT update per dimension → mapped KC (score ≥ _PASS_DIM = correct observation).
    mastery_updates = []
    for dim, kc_id in _DIM_TO_KC.items():
        score = result["scores"].get(dim, 0)
        upd = bkt.observe(session_id, kc_id, score >= _PASS_DIM)
        mastery_updates.append(
            {
                "kc_id": kc_id,
                "kc_name": upd.get("name"),
                "dimension": dim,
                "dimension_score": score,
                "mastery_before": upd.get("mastery_before"),
                "mastery_after": upd.get("mastery_after"),
                "color": upd.get("color"),
            }
        )

    result["scenario_id"] = scenario_id
    result["mastery_updates"] = mastery_updates
    result["recommended_next"] = bkt.recommend_next(session_id)
    # Reveal the reference approach now that the learner has submitted.
    result["ideal_approach"] = scenario.get("ideal_approach", [])
    return result
