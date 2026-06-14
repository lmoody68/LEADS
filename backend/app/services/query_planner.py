"""
LLM Query Planner (MasterBuildPlan §3.1 — "query rewriting for legal
specificity") for L.E.A.D.S.

Given a user's natural-language legal question, asks the LLM to produce a small
JSON plan that drives downstream retrieval:

    {
      "search_query": "<tightened query for CourtListener + keyword search>",
      "legal_issues": ["<the legal issue(s) at stake>", ...],
      "jurisdiction_hint": "<federal | a state | '' if none>"
    }

Example:
    "What did Heintz v. Jenkins hold?"
      -> search_query: "Heintz v. Jenkins FDCPA attorney debt collector"
         legal_issues: ["Whether the FDCPA applies to litigating attorneys"]
         jurisdiction_hint: "federal"

GUARDRAIL: this is a stateless completion call (the LLM router never trains on
or retains data). DETERMINISTIC FALLBACK: if no LLM key is configured or the
output can't be parsed, we return a plan built from the raw question so the
pipeline still works with zero keys.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from . import llm_router

_PLANNER_SYSTEM = (
    "You are a legal research query planner. Given a user's question, produce a "
    "compact retrieval plan as STRICT JSON only (no markdown, no prose, no code "
    "fences). The JSON must have exactly these keys: "
    '{"search_query": "...", "legal_issues": ["..."], "jurisdiction_hint": "..."}. '
    "Rules: "
    "search_query = a tightened search string optimized for a case-law database "
    "(include party names, the controlling statute/doctrine, and key terms; drop "
    "filler words like 'what did' / 'hold'). "
    "legal_issues = 1-3 short statements of the legal question(s) at stake. "
    "jurisdiction_hint = 'federal', a U.S. state name, or '' if unclear. "
    "Do NOT answer the question. Only plan the search."
)


def _extract_json(raw: str) -> Dict[str, Any] | None:
    """Pull a JSON object out of an LLM response that may wrap it in fences/prose."""
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


def _deterministic_plan(question: str) -> Dict[str, Any]:
    """No-LLM fallback: use the raw question as the search query."""
    q = question.strip()
    # Light heuristic for jurisdiction.
    juris = ""
    if re.search(r"\bfederal\b|U\.?S\.?C\.?|Supreme Court|Circuit\b", q, re.IGNORECASE):
        juris = "federal"
    return {
        "search_query": q,
        "legal_issues": [q],
        "jurisdiction_hint": juris,
        "planner": "deterministic (no LLM key)",
    }


def plan(question: str) -> Dict[str, Any]:
    """
    Return a retrieval plan for the question. Always returns a dict with
    search_query (str), legal_issues (list[str]), jurisdiction_hint (str),
    and a `planner` label noting which path produced it.
    """
    question = (question or "").strip()
    if not question:
        return {"search_query": "", "legal_issues": [], "jurisdiction_hint": "", "planner": "empty"}

    raw, provider = llm_router.synthesize(_PLANNER_SYSTEM, f"Question: {question}")
    parsed = _extract_json(raw) if raw else None
    if not parsed or not isinstance(parsed, dict):
        return _deterministic_plan(question)

    search_query = str(parsed.get("search_query") or question).strip() or question
    issues_raw = parsed.get("legal_issues") or []
    if isinstance(issues_raw, str):
        issues_raw = [issues_raw]
    legal_issues: List[str] = [str(i).strip() for i in issues_raw if str(i).strip()][:3]
    if not legal_issues:
        legal_issues = [question]
    jurisdiction = str(parsed.get("jurisdiction_hint") or "").strip()

    return {
        "search_query": search_query,
        "legal_issues": legal_issues,
        "jurisdiction_hint": jurisdiction,
        "planner": provider,
    }
