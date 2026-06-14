"""
Compliance & Ethics Advisor (MasterBuildPlan §3.5) for L.E.A.D.S.

A TEACHING / ADVISORY tool that reasons over a user-described investigative
scenario and explains WHEN an investigative method is lawful vs. unlawful, then
recommends COMPLIANT paths. It is grounded in the real public statutory seed
corpus (FDCPA, FCRA, DPPA, GLBA) via the existing Phase-1 hybrid retrieval, and
it uses the existing free-first `llm_router`.

PIPELINE:
    1. Retrieve — reuse `rag.hybrid_retrieve` over the seeded statutes to pull
       the governing statutory text relevant to the scenario.
    2. Analyze  — LLM produces a STRUCTURED legal-analysis JSON: permissible
       purpose verdict, governing statutes, restrictions, risk flags, COMPLIANT
       alternatives, citations, and a disclaimer.
    3. Fallback — with NO LLM key, a deterministic/extractive analysis is built
       from the retrieved statutes + a template (still useful, never crashes).

⚠️ SPECIAL GUARDRAIL (non-negotiable, baked into the prompt + post-processing):
  * This is EDUCATION, not an operations manual. It NEVER produces a how-to for
    unlawful skip tracing / PII gathering. For an UNLAWFUL scenario it explains
    *why* the method is impermissible and points to the LAWFUL alternative.
  * Output is general legal INFORMATION, not legal advice (disclaimer always
    attached, including in the fallback path).
  * No PII, no scraping, nothing trains on the data (stateless LLM calls). This
    module adds NO new data sources — it only reads the existing seed corpus.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from . import llm_router, rag

# Retrieve a few statutory passages to ground the analysis.
_RETRIEVE_K = 6


# ---------------------------------------------------------------------------
# Shared JSON extraction (mirrors rag/agent_memo — LLMs love code fences).
# ---------------------------------------------------------------------------
def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    if not fenced:
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = brace.group(0) if brace else candidate
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


DISCLAIMER = (
    "This is general legal information for educational purposes, NOT legal advice. "
    "It does not create an attorney-client relationship. Laws vary by jurisdiction "
    "and change over time; consult a licensed attorney before acting on any "
    "investigative or debt-collection matter."
)


# ---------------------------------------------------------------------------
# STEP 1 — Retrieve the governing statutory text.
# ---------------------------------------------------------------------------
def _retrieve_statutes(scenario: str) -> List[Dict[str, Any]]:
    """Hybrid-retrieve relevant seeded statutory passages for the scenario."""
    hits, _debug = rag.hybrid_retrieve(scenario, k=_RETRIEVE_K)
    return hits


def _format_passages(hits: List[Dict[str, Any]]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(
            f"[{i}] {h.get('source_title','')}\n"
            f"    Citation: {h.get('citation','')}\n"
            f"    Passage: {h.get('snippet','')}"
        )
    return "\n\n".join(lines)


def _citations_from_hits(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for h in hits:
        snippet = h.get("snippet", "") or ""
        out.append(
            {
                "source_title": h.get("source_title", ""),
                "citation": h.get("citation", ""),
                "url": h.get("url", "") or _cornell_url(h.get("citation", "")),
                "snippet": snippet[:400] + ("…" if len(snippet) > 400 else ""),
            }
        )
    return out


# Map a few known U.S.C. citations to a Cornell LII URL for the UI (best-effort).
# Capture the section number PLUS any trailing statutory subsection letter(s)
# (e.g. "§ 1681b" → section "1681b") so the URL points at the right provision —
# Cornell LII addresses these as /uscode/text/15/1681b, not /15/1681.
_USC_RE = re.compile(r"(\d+)\s*U\.?S\.?C\.?\s*§*\s*(\d+[a-z]*)", re.IGNORECASE)


def _cornell_url(citation: str) -> str:
    m = _USC_RE.search(citation or "")
    if not m:
        return ""
    title, section = m.group(1), m.group(2).lower()
    return f"https://www.law.cornell.edu/uscode/text/{title}/{section}"


# ---------------------------------------------------------------------------
# STEP 2 — LLM structured analysis (teaching/advisory framing).
# ---------------------------------------------------------------------------
_ANALYSIS_SYSTEM = (
    "You are the COMPLIANCE & ETHICS ADVISOR of L.E.A.D.S., a TEACHING tool for "
    "investigators, paralegals, and debt-collection professionals. Your job is to "
    "EXPLAIN when an investigative method is LAWFUL vs. UNLAWFUL and to recommend "
    "COMPLIANT paths, grounded ONLY in the numbered statutory passages provided "
    "(FDCPA, FCRA, DPPA, GLBA).\n\n"
    "ABSOLUTE RULES:\n"
    "- You are EDUCATIONAL, not an operations manual. NEVER provide step-by-step "
    "instructions for an UNLAWFUL method (e.g., pretexting, buying DMV data, "
    "scraping PII, lying to obtain location info). If the scenario is unlawful, "
    "explain WHY it is impermissible (which statute it violates) and point to the "
    "LAWFUL alternative instead.\n"
    "- Ground every statutory claim in a numbered passage and cite it inline by "
    "[n] in your explanations.\n"
    "- This is general legal information, not legal advice.\n\n"
    "Respond with STRICT JSON ONLY (no markdown, no code fences, no prose outside "
    "the JSON) of exactly this shape:\n"
    "{\n"
    '  "permissible_purpose": {"verdict": "yes" | "no" | "depends", '
    '"explanation": "1-3 sentences citing [n]"},\n'
    '  "governing_statutes": [{"name": "...", "citation": "...", '
    '"why": "why it governs this scenario, cite [n]"}],\n'
    '  "restrictions": ["specific restriction the law imposes, cite [n]", "..."],\n'
    '  "risk_flags": ["concrete legal/ethical risk if done wrong, e.g. DPPA '
    'criminal/civil liability, FDCPA third-party disclosure violation", "..."],\n'
    '  "compliant_alternatives": ["a LAWFUL way to accomplish the legitimate goal, '
    'cite the permissible purpose [n]", "..."],\n'
    '  "disclaimer": "general legal information, not legal advice"\n'
    "}\n"
    "verdict guidance: 'yes' = a permissible purpose clearly exists; 'no' = the "
    "described method is impermissible as framed; 'depends' = lawful only if "
    "specific conditions/permissible purposes are met (spell them out). Keep lists "
    "concrete and tied to the passages. Do not invent statutes not in the passages."
)


def _analyze_llm(scenario: str, hits: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    user = (
        f"Investigative scenario described by the user:\n{scenario}\n\n"
        f"Governing statutory passages (cite by [n]):\n{_format_passages(hits)}\n\n"
        "Produce the structured compliance analysis as STRICT JSON. Remember: if "
        "the method is unlawful, explain WHY and give the lawful alternative — do "
        "NOT explain how to do the unlawful thing."
    )
    raw, provider = llm_router.synthesize(_ANALYSIS_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None
    if not parsed:
        return None
    parsed["provider"] = provider
    return parsed


# ---------------------------------------------------------------------------
# STEP 3 — Deterministic fallback (no LLM key).
# ---------------------------------------------------------------------------
def _normalize_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _detect_dppa(scenario: str, hits: List[Dict[str, Any]]) -> bool:
    s = scenario.lower()
    dmv = any(
        t in s
        for t in ("dmv", "motor vehicle", "driver's license", "drivers license", "license plate", "vehicle record")
    )
    return dmv or any("2721" in (h.get("citation") or "") for h in hits)


def _analyze_deterministic(scenario: str, hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    No-LLM fallback: build a conservative, statute-grounded template. It does NOT
    attempt to definitively rule the scenario lawful — it surfaces the governing
    statutes + permissible-purpose framework and steers toward compliant paths,
    flagging the obvious DPPA/FDCPA tripwires extractively.
    """
    s = scenario.lower()
    governing: List[Dict[str, Any]] = []
    seen = set()
    for h in hits:
        cite = h.get("citation", "")
        if cite and cite not in seen:
            seen.add(cite)
            governing.append(
                {
                    "name": h.get("source_title", ""),
                    "citation": cite,
                    "why": "Retrieved as relevant to the scenario; review the passage in Citations below.",
                }
            )

    restrictions: List[str] = []
    risk_flags: List[str] = []
    alternatives: List[str] = []

    is_dppa = _detect_dppa(scenario, hits)
    is_debt = any(t in s for t in ("debt", "collector", "collection", "creditor", "judgment"))

    if is_dppa:
        risk_flags.append(
            "Obtaining personal information from state motor-vehicle (DMV) records is "
            "restricted by the DPPA (18 U.S.C. § 2721) and is impermissible unless a "
            "statutory permissible use applies; misuse carries criminal and civil liability."
        )
        restrictions.append(
            "DPPA permits release of DMV personal information only for enumerated uses "
            "(e.g., court/government function, use in litigation, or by a LICENSED "
            "investigator for a permitted purpose) — never to 'confront' or harass."
        )
        alternatives.append(
            "Use a DPPA-permissible channel: formal litigation discovery / subpoena, "
            "service-of-process needs, or a licensed PI acting for a permitted purpose."
        )

    if is_debt:
        restrictions.append(
            "Under the FDCPA, third-party 'location information' contacts (§ 1692b) may "
            "not reveal the debt, may generally occur only once per third party, and "
            "must route through the consumer's attorney if known (§ 1692c)."
        )
        alternatives.append(
            "For a debtor's employer/address: use FDCPA § 1692b location-information "
            "calls (without disclosing the debt), public-record / litigation tools, or "
            "an FCRA-permissible-purpose channel (§ 1681b) such as account collection."
        )
        risk_flags.append(
            "Disclosing the debt to a third party, or obtaining a consumer report "
            "without an FCRA permissible purpose (§ 1681b(f)), creates FDCPA/FCRA liability."
        )

    if not alternatives:
        alternatives.append(
            "Identify a lawful permissible purpose first, then use only public records, "
            "consented data, or a statutorily-permitted channel to obtain the information."
        )

    # Word-boundary match so "ex" (former partner) only triggers on the standalone
    # word — not on substrings inside "expense", "next", "complex", "context", etc.
    personal_target = bool(re.search(r"\b(?:ex|confront|harass|stalk)\b", s))
    verdict = "no" if is_dppa and personal_target else "depends"
    if verdict == "no":
        explanation = (
            "As framed, the method is impermissible: it seeks DMV personal information "
            "for a purpose the DPPA does not allow. See the governing statutes and the "
            "compliant alternatives below."
        )
    else:
        explanation = (
            "Whether a permissible purpose exists depends on HOW the information is "
            "obtained and for WHAT use. Review the governing statutes below and choose "
            "a statutorily-permitted channel; the compliant alternatives list lawful options."
        )

    return {
        "permissible_purpose": {"verdict": verdict, "explanation": explanation},
        "governing_statutes": governing,
        "restrictions": restrictions
        or ["Review the retrieved statutory passages below for the applicable restrictions."],
        "risk_flags": risk_flags
        or ["Acting without a statutory permissible purpose can create civil and/or criminal liability."],
        "compliant_alternatives": alternatives,
        "disclaimer": DISCLAIMER,
        "provider": "extractive (no LLM key)",
    }


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------
def analyze(scenario: str) -> Dict[str, Any]:
    """
    Analyze an investigative scenario for legal compliance.

    Returns:
      {
        scenario,
        permissible_purpose: {verdict: "yes"|"no"|"depends", explanation},
        governing_statutes: [{name, citation, why}],
        restrictions: [...],
        risk_flags: [...],
        compliant_alternatives: [...],
        citations: [{source_title, citation, url, snippet}],
        disclaimer,
        provider
      }
    """
    scenario = (scenario or "").strip()
    hits = _retrieve_statutes(scenario)

    if not hits:
        return {
            "scenario": scenario,
            "permissible_purpose": {
                "verdict": "depends",
                "explanation": "No statutory passages were retrieved, so no grounded analysis is possible.",
            },
            "governing_statutes": [],
            "restrictions": [],
            "risk_flags": [],
            "compliant_alternatives": [
                "Re-describe the scenario with more detail (who is seeking what information, "
                "for what purpose) so the advisor can identify the governing statute."
            ],
            "citations": [],
            "disclaimer": DISCLAIMER,
            "provider": "none",
        }

    parsed = _analyze_llm(scenario, hits)
    if parsed is None:
        result = _analyze_deterministic(scenario, hits)
    else:
        pp = parsed.get("permissible_purpose") or {}
        if isinstance(pp, str):
            pp = {"verdict": "depends", "explanation": pp}
        verdict = str(pp.get("verdict", "depends")).strip().lower()
        if verdict not in ("yes", "no", "depends"):
            verdict = "depends"
        governing_raw = parsed.get("governing_statutes") or []
        governing: List[Dict[str, Any]] = []
        if isinstance(governing_raw, list):
            for g in governing_raw:
                if isinstance(g, dict):
                    governing.append(
                        {
                            "name": str(g.get("name", "")).strip(),
                            "citation": str(g.get("citation", "")).strip(),
                            "why": str(g.get("why", "")).strip(),
                            "url": _cornell_url(str(g.get("citation", ""))),
                        }
                    )
        result = {
            "permissible_purpose": {
                "verdict": verdict,
                "explanation": str(pp.get("explanation", "")).strip(),
            },
            "governing_statutes": governing,
            "restrictions": _normalize_list(parsed.get("restrictions")),
            "risk_flags": _normalize_list(parsed.get("risk_flags")),
            "compliant_alternatives": _normalize_list(parsed.get("compliant_alternatives")),
            "disclaimer": str(parsed.get("disclaimer") or "").strip() or DISCLAIMER,
            "provider": parsed.get("provider", "llm"),
        }

    # Always attach the grounding citations + scenario, and guarantee the disclaimer.
    result["scenario"] = scenario
    result["citations"] = _citations_from_hits(hits)
    if not result.get("disclaimer"):
        result["disclaimer"] = DISCLAIMER
    return result
