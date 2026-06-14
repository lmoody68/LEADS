"""
Agentic Research Memo (MasterBuildPlan §3.2) for L.E.A.D.S.

A transparent, multi-step AGENT — implemented as a clean, deterministic state
machine (NOT LangChain) — that plans, researches, synthesizes, drafts, cites,
and self-reviews a structured legal research memo.

PIPELINE (state machine):
    1. Planner     — LLM decomposes the question into 2-4 focused sub-questions.
    2. Retriever   — for EACH sub-question, reuse the Phase-1 hybrid retrieval
                     (dense+BM25+RRF) over statutes + live CourtListener case
                     law. Collect a deduped pool of REAL sources.
    3. Synthesizer — LLM merges findings across sub-questions; notes agreements,
                     flags conflicts and gaps.
    4. Drafter     — LLM writes a structured memo (Issue(s) / Brief Answer /
                     Facts & Background / Analysis / Conclusion) with inline
                     [n; citation] markers tied to the numbered source pool.
    5. Citer       — verify every section carries an inline citation tied to a
                     REAL retrieved source; assemble the final ordered sources
                     list. Drops markers that point at non-existent sources.
    6. Reviewer    — LLM self-check for unsupported/hallucinated claims, missing
                     citations, logical consistency; returns flags + a confidence
                     label per section.

DESIGN PRINCIPLES (per the build brief):
  * REUSE the existing infrastructure — `rag.hybrid_retrieve` /
    `rag.ingest_courtlistener` for retrieval and `llm_router.synthesize` for all
    LLM calls (free-first Groq -> Gemini -> Claude). NO LangChain, NO new
    provider logic. A transparent custom state machine is preferred for
    reliability and auditability.
  * GRACEFUL DEGRADE: with NO LLM key, every LLM step has a deterministic /
    extractive fallback so the agent still produces a usable memo (it does NOT
    crash). The plan, the synthesis, the draft, and the review all degrade.

GUARDRAILS (inherited from the rest of the service):
  * PUBLIC / licensed legal data ONLY (seeded statutes + CourtListener opinions).
  * No PII, no scraping. Nothing trains on the data (stateless LLM calls).
  * Everything stays local. This module adds NO new data sources.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from . import llm_router, query_planner, rag

# How many sources to retrieve per sub-question, and the cap on the merged pool.
_PER_SUBQ_K = 4
_MAX_POOL = 10


# ---------------------------------------------------------------------------
# Shared JSON extraction (mirrors rag/query_planner — LLMs love code fences).
# ---------------------------------------------------------------------------
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


# ===========================================================================
# STEP 1 — PLANNER
# ===========================================================================
_PLANNER_SYSTEM = (
    "You are the PLANNER of a legal research agent. Decompose the user's research "
    "question into 2 to 4 FOCUSED, non-overlapping sub-questions that, answered "
    "together, fully resolve it. Each sub-question must be independently "
    "researchable in a case-law / statute database. Respond with STRICT JSON only "
    "(no markdown, no prose, no code fences) of the form: "
    '{"sub_questions": ["...", "..."]}. '
    "Order them logically (threshold/definitional issues first, then exceptions/"
    "limits, then remedies). Do NOT answer them."
)


def _plan(question: str) -> Tuple[List[str], str]:
    """Decompose the question into 2-4 sub-questions. Returns (sub_qs, planner_label)."""
    raw, provider = llm_router.synthesize(_PLANNER_SYSTEM, f"Research question: {question}")
    parsed = _extract_json(raw) if raw else None
    subqs: List[str] = []
    if isinstance(parsed, dict):
        sq = parsed.get("sub_questions") or []
        if isinstance(sq, list):
            subqs = [str(s).strip() for s in sq if str(s).strip()]
    elif isinstance(parsed, list):
        subqs = [str(s).strip() for s in parsed if str(s).strip()]

    subqs = subqs[:4]
    if len(subqs) >= 2:
        return subqs, provider

    # Deterministic fallback: derive sub-questions from the planner's legal issues
    # (itself LLM-or-deterministic) so we still have a real multi-step plan.
    qplan = query_planner.plan(question)
    issues = qplan.get("legal_issues") or []
    fallback = [question.strip()]
    for iss in issues:
        if iss.strip() and iss.strip().lower() != question.strip().lower():
            fallback.append(iss.strip())
    if len(fallback) < 2:
        fallback.append("What are the key exceptions, limits, or defenses to the rule at issue?")
    return fallback[:4], (provider if provider != "extractive (no LLM key)" else "deterministic (no LLM key)")


# ===========================================================================
# STEP 2 — RETRIEVER (reuses Phase-1 hybrid retrieval + CourtListener)
# ===========================================================================
def _source_key(hit: Dict[str, Any]) -> str:
    """Dedupe key for a retrieved source (citation + first 60 chars of snippet)."""
    return f"{hit.get('citation','')}::{(hit.get('snippet') or '')[:60]}"


def _retrieve_pool(
    question: str, sub_questions: List[str], deep: bool
) -> Tuple[List[Dict[str, Any]], Dict[str, List[int]], List[Dict[str, Any]]]:
    """
    For each sub-question, (optionally) pull live CourtListener case law into the
    shared collection, then run Phase-1 hybrid retrieval. Merge into a deduped,
    ordered source pool.

    Returns:
      pool          — ordered, deduped list of source hits (the memo's [n] map).
      subq_sources  — {sub_question: [1-based indices into pool]} for transparency.
      ingested_meta — live opinions pulled from CourtListener.
    """
    pool: List[Dict[str, Any]] = []
    key_to_idx: Dict[str, int] = {}
    subq_sources: Dict[str, List[int]] = {}
    ingested_meta: List[Dict[str, Any]] = []
    seen_ingest: set[str] = set()

    for subq in sub_questions:
        # 2a. On-demand live case law for this sub-question (deep mode only).
        if deep:
            # Plan a tight search string for this sub-question, like the RAG engine.
            sq_plan = query_planner.plan(subq)
            search_query = sq_plan.get("search_query") or subq
            for op in rag.ingest_courtlistener(search_query):
                url = op.get("url", "")
                if url and url in seen_ingest:
                    continue
                seen_ingest.add(url)
                ingested_meta.append(
                    {
                        "case_name": op.get("case_name", ""),
                        "citation": op.get("citation", ""),
                        "court": op.get("court", ""),
                        "date": op.get("date", ""),
                        "url": url,
                        "for_sub_question": subq,
                    }
                )

        # 2b. Hybrid retrieval over statutes + any fetched opinions.
        hits, _debug = rag.hybrid_retrieve(subq, k=_PER_SUBQ_K)
        idxs: List[int] = []
        for h in hits:
            key = _source_key(h)
            if key in key_to_idx:
                idx = key_to_idx[key]
            else:
                if len(pool) >= _MAX_POOL:
                    continue
                pool.append(h)
                idx = len(pool)  # 1-based
                key_to_idx[key] = idx
            if idx not in idxs:
                idxs.append(idx)
        subq_sources[subq] = idxs

    return pool, subq_sources, ingested_meta


def _format_pool(pool: List[Dict[str, Any]]) -> str:
    """Numbered source block the LLM cites by [n; citation]."""
    lines = []
    for i, h in enumerate(pool, 1):
        kind = "Opinion" if h.get("doc_type") == "opinion" else "Statute"
        court = f" ({h['court']}, {h['date']})" if h.get("court") else ""
        sect = f" [{h['legal_section']}]" if h.get("legal_section") and h.get("doc_type") == "opinion" else ""
        lines.append(
            f"[{i}] {kind}{sect}: {h.get('source_title','')}{court}\n"
            f"    Citation: {h.get('citation','')}\n"
            f"    Passage: {h.get('snippet','')}"
        )
    return "\n\n".join(lines)


def _subq_map_text(subq_sources: Dict[str, List[int]]) -> str:
    return "\n".join(
        f"- {sq}  -> sources {srcs or '[none retrieved]'}" for sq, srcs in subq_sources.items()
    )


# ===========================================================================
# STEP 3 — SYNTHESIZER
# ===========================================================================
_SYNTH_SYSTEM = (
    "You are the SYNTHESIZER of a legal research agent. You are given the research "
    "question, its sub-questions (each mapped to the numbered source passages that "
    "are relevant to it), and the full numbered source pool. Merge the findings "
    "ACROSS the sub-questions into a single coherent picture, USING ONLY the "
    "numbered passages. Respond with STRICT JSON only (no markdown, no code "
    "fences): "
    '{"findings": ["a finding with its [n; citation] support", "..."], '
    '"conflicts": ["where sources disagree or one qualifies another", "..."], '
    '"gaps": ["questions the retrieved sources do NOT cover", "..."]}. '
    "Every finding must cite at least one source by its [n] number. Do not invent "
    "sources. conflicts/gaps may be empty lists."
)


def _synthesize(
    question: str, subq_sources: Dict[str, List[int]], pool: List[Dict[str, Any]]
) -> Tuple[List[str], List[str], List[str], str]:
    """Returns (findings, conflicts, gaps, provider)."""
    user = (
        f"Research question: {question}\n\n"
        f"Sub-questions -> relevant source numbers:\n{_subq_map_text(subq_sources)}\n\n"
        f"Source pool:\n{_format_pool(pool)}"
    )
    raw, provider = llm_router.synthesize(_SYNTH_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None
    if isinstance(parsed, dict):
        findings = [str(x).strip() for x in (parsed.get("findings") or []) if str(x).strip()]
        conflicts = [str(x).strip() for x in (parsed.get("conflicts") or []) if str(x).strip()]
        gaps = [str(x).strip() for x in (parsed.get("gaps") or []) if str(x).strip()]
        if findings:
            return findings, conflicts, gaps, provider

    # Deterministic fallback: one finding per source, verbatim + cited.
    findings = [
        f"{h.get('source_title','')} ({'opinion' if h.get('doc_type')=='opinion' else 'statute'}) "
        f"states: {(h.get('snippet') or '')[:240]}… [{i}; {h.get('citation','')}]"
        for i, h in enumerate(pool, 1)
    ]
    return findings, [], [], "deterministic (no LLM key)"


# ===========================================================================
# STEP 4 — DRAFTER
# ===========================================================================
_MEMO_SECTIONS = ["Issue(s)", "Brief Answer", "Facts & Background", "Analysis", "Conclusion"]

_DRAFT_SYSTEM = (
    "You are the DRAFTER of a legal research agent. Write a STRUCTURED legal "
    "research memo answering the research question, USING ONLY the numbered source "
    "passages provided. The memo MUST have exactly these five sections, each "
    "introduced by a markdown H2 header on its own line, in this order:\n"
    "## Issue(s)\n## Brief Answer\n## Facts & Background\n## Analysis\n## Conclusion\n\n"
    "Requirements:\n"
    "- Ground EVERY substantive assertion in the sources and cite inline in "
    "brackets by number AND citation, e.g. [1; 15 U.S.C. § 1692c(b)] or "
    "[2; Heintz v. Jenkins, 514 U.S. 291].\n"
    "- In Analysis, address each sub-question / legal issue; note where sources "
    "AGREE and explicitly FLAG any conflict or qualification.\n"
    "- Use the synthesized findings, conflicts, and gaps provided. If the sources "
    "do not cover something, say so in Conclusion — do NOT speculate beyond them.\n"
    "- This is general legal information, not legal advice. Be precise and concise. "
    "Output ONLY the markdown memo (no preamble, no code fences)."
)


def _draft(
    question: str,
    sub_questions: List[str],
    findings: List[str],
    conflicts: List[str],
    gaps: List[str],
    pool: List[Dict[str, Any]],
) -> Tuple[str, str]:
    """Returns (memo_markdown, provider)."""
    user = (
        f"Research question: {question}\n\n"
        f"Sub-questions:\n" + "\n".join(f"- {s}" for s in sub_questions) + "\n\n"
        f"Synthesized findings:\n" + "\n".join(f"- {f}" for f in findings) + "\n\n"
        f"Noted conflicts: {conflicts or 'none'}\n"
        f"Noted gaps: {gaps or 'none'}\n\n"
        f"Source pool (cite by [n; citation]):\n{_format_pool(pool)}"
    )
    text, provider = llm_router.synthesize(_DRAFT_SYSTEM, user)
    if text:
        return text.strip(), provider
    return _extractive_memo(question, sub_questions, findings, conflicts, gaps, pool), "extractive (no LLM key)"


def _extractive_memo(
    question: str,
    sub_questions: List[str],
    findings: List[str],
    conflicts: List[str],
    gaps: List[str],
    pool: List[Dict[str, Any]],
) -> str:
    """No-LLM fallback: assemble a structured, fully-cited memo from retrieved passages."""
    out: List[str] = []
    out.append("## Issue(s)")
    out.append(f"This memo addresses: {question}")
    out.append("The research was decomposed into the following sub-issues:")
    out += [f"- {s}" for s in sub_questions]
    out.append("")

    out.append("## Brief Answer")
    out.append(
        "No LLM provider key is configured, so this memo is assembled EXTRACTIVELY "
        "from the most relevant retrieved authorities. Each statement below is a "
        "verbatim, cited passage rather than synthesized prose."
    )
    out.append("")

    out.append("## Facts & Background")
    out.append(
        "No external facts were supplied; the analysis proceeds from the controlling "
        "public statutes and court opinions retrieved for the question."
    )
    out.append("")

    out.append("## Analysis")
    if findings:
        out += [f"- {f}" for f in findings]
    else:
        for i, h in enumerate(pool, 1):
            out.append(
                f"- {h.get('source_title','')}: {(h.get('snippet') or '')[:260]}… "
                f"[{i}; {h.get('citation','')}]"
            )
    if conflicts:
        out.append("")
        out.append("**Conflicts / qualifications between sources:**")
        out += [f"- {c}" for c in conflicts]
    out.append("")

    out.append("## Conclusion")
    if gaps:
        out.append("The retrieved authorities do not fully cover: " + "; ".join(gaps) + ".")
    out.append(
        "The cited passages above are the strongest retrieved authorities on point. "
        "This is general legal information, not legal advice."
    )
    return "\n".join(out)


# ===========================================================================
# STEP 5 — CITER (verify markers point at real retrieved sources)
# ===========================================================================
_SECTION_HEADER_RE = re.compile(r"^\s*#{1,6}\s*(.+?)\s*$", re.MULTILINE)
_CITE_MARKER_RE = re.compile(r"\[(\d+)(?:;[^\]]*)?\]")


def _split_sections(memo_md: str) -> List[Tuple[str, str]]:
    """Split a markdown memo into [(title, body)] on H1-H6 headers."""
    matches = list(_SECTION_HEADER_RE.finditer(memo_md))
    if not matches:
        return [("Memo", memo_md.strip())]
    sections: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(memo_md)
        sections.append((title, memo_md[start:end].strip()))
    return sections


def _cite(memo_md: str, pool: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Verify inline [n] markers reference a real source in the pool. Markers that
    point past the pool are dropped (with a note). Returns:
      cleaned_memo, ordered_sources_list, citer_notes.
    """
    notes: List[str] = []
    pool_size = len(pool)

    def _scrub(match: re.Match) -> str:
        n = int(match.group(1))
        if 1 <= n <= pool_size:
            return match.group(0)
        notes.append(f"Removed citation marker {match.group(0)} — no source #{n} exists.")
        return ""

    cleaned = _CITE_MARKER_RE.sub(_scrub, memo_md)

    # Which sources are actually cited anywhere in the memo?
    used = sorted({int(m.group(1)) for m in _CITE_MARKER_RE.finditer(cleaned) if 1 <= int(m.group(1)) <= pool_size})
    if not used:
        notes.append("No inline citations were found in the draft; all retrieved sources are listed for reference.")

    # Final ordered sources list = the full pool, in [n] order, with required fields.
    sources: List[Dict[str, Any]] = []
    for i, h in enumerate(pool, 1):
        sources.append(
            {
                "n": i,
                "source_title": h.get("source_title", ""),
                "citation": h.get("citation", ""),
                "doc_type": h.get("doc_type", "statute"),
                "court": h.get("court", ""),
                "date": h.get("date", ""),
                "url": h.get("url", ""),
                "legal_section": h.get("legal_section", ""),
                "snippet": h.get("snippet", ""),
                "score": h.get("score", 0),
                "cited": i in used,
            }
        )
    return cleaned, sources, notes


# ===========================================================================
# STEP 6 — REVIEWER (self-check)
# ===========================================================================
_REVIEW_SYSTEM = (
    "You are the REVIEWER of a legal research agent — an adversarial self-check. "
    "You are given a drafted memo (with inline [n; citation] markers) and the "
    "numbered source pool the markers refer to. Audit the memo for: (a) "
    "UNSUPPORTED or HALLUCINATED claims (assertions with no citation, or citing a "
    "source that does not support them), (b) MISSING citations, (c) LOGICAL "
    "inconsistencies. Then assign a confidence label to EACH memo section. Respond "
    "with STRICT JSON only (no markdown, no code fences): "
    '{"notes": ["specific issue found", "..."], '
    '"section_confidence": {"Issue(s)": "high|medium|low", "Brief Answer": "...", '
    '"Facts & Background": "...", "Analysis": "...", "Conclusion": "..."}}. '
    "Use 'high' when every claim maps to a cited source, 'medium' when mostly "
    "grounded with minor gaps, 'low' when claims are unsupported. If the memo is "
    "clean, notes may be an empty list."
)


def _review(
    memo_md: str, sections: List[Tuple[str, str]], pool: List[Dict[str, Any]]
) -> Tuple[List[str], Dict[str, str], str]:
    """Returns (reviewer_notes, {section_title: confidence}, provider)."""
    user = (
        f"Memo:\n{memo_md}\n\n"
        f"Source pool the [n] markers refer to:\n{_format_pool(pool)}"
    )
    raw, provider = llm_router.synthesize(_REVIEW_SYSTEM, user)
    parsed = _extract_json(raw) if raw else None

    notes: List[str] = []
    conf: Dict[str, str] = {}
    if isinstance(parsed, dict):
        notes = [str(x).strip() for x in (parsed.get("notes") or []) if str(x).strip()]
        sc = parsed.get("section_confidence") or {}
        if isinstance(sc, dict):
            conf = {str(k).strip(): str(v).strip().lower() for k, v in sc.items() if str(v).strip()}

    if conf:
        return notes, conf, provider

    # Deterministic fallback: confidence from inline-citation density per section.
    conf = {}
    det_notes: List[str] = list(notes)
    for title, body in sections:
        n_cites = len(_CITE_MARKER_RE.findall(body))
        if n_cites >= 2:
            conf[title] = "high"
        elif n_cites == 1:
            conf[title] = "medium"
        else:
            conf[title] = "low"
            if body.strip():
                det_notes.append(f"Section '{title}' has no inline citations — treat as unsupported.")
    return det_notes, conf, "deterministic (no LLM key)"


# ===========================================================================
# ORCHESTRATOR — runs the full state machine
# ===========================================================================
def generate_memo(question: str, deep: bool = True) -> Dict[str, Any]:
    """
    Run the full agent pipeline and return the memo object:

      {
        question, deep,
        plan: [sub_questions],
        subq_sources: {sub_q: [source #s]},
        memo_markdown,
        sections: [{title, body, confidence}],
        sources: [{n, source_title, citation, court, date, url, snippet, cited, ...}],
        findings, conflicts, gaps, reviewer_notes, citer_notes,
        grounding, provider, providers,
        ingested
      }
    """
    question = (question or "").strip()
    providers: Dict[str, str] = {}

    # 1. PLANNER
    sub_questions, providers["planner"] = _plan(question)

    # 2. RETRIEVER
    pool, subq_sources, ingested = _retrieve_pool(question, sub_questions, deep)

    if not pool:
        msg = (
            "No sources could be retrieved for any sub-question, so there is "
            "nothing to ground a memo on."
        )
        return {
            "question": question,
            "deep": deep,
            "plan": sub_questions,
            "subq_sources": subq_sources,
            "memo_markdown": f"## Issue(s)\n{question}\n\n## Conclusion\n{msg}",
            "sections": [
                {"title": "Issue(s)", "body": question, "confidence": "low"},
                {"title": "Conclusion", "body": msg, "confidence": "low"},
            ],
            "sources": [],
            "findings": [],
            "conflicts": [],
            "gaps": [msg],
            "reviewer_notes": [msg],
            "citer_notes": [],
            "grounding": "No sources retrieved.",
            "provider": providers["planner"],
            "providers": providers,
            "ingested": ingested,
        }

    # 3. SYNTHESIZER
    findings, conflicts, gaps, providers["synthesizer"] = _synthesize(question, subq_sources, pool)

    # 4. DRAFTER
    memo_md, providers["drafter"] = _draft(question, sub_questions, findings, conflicts, gaps, pool)

    # 5. CITER
    memo_md, sources, citer_notes = _cite(memo_md, pool)

    # 6. REVIEWER
    section_pairs = _split_sections(memo_md)
    reviewer_notes, section_conf, providers["reviewer"] = _review(memo_md, section_pairs, pool)

    # Attach per-section confidence (case-insensitive title match; default medium).
    conf_lc = {k.lower(): v for k, v in section_conf.items()}
    sections_out: List[Dict[str, str]] = []
    for title, body in section_pairs:
        confidence = conf_lc.get(title.lower(), "medium")
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"
        sections_out.append({"title": title, "body": body, "confidence": confidence})

    # A primary provider label for the UI badge: prefer the drafter's.
    primary = providers.get("drafter", "extractive (no LLM key)")

    n_cited = sum(1 for s in sources if s.get("cited"))
    grounding = (
        f"Memo grounded in {len(sources)} retrieved authorities ({n_cited} cited inline) "
        f"across {len(sub_questions)} sub-questions via hybrid dense+BM25+RRF retrieval."
    )

    return {
        "question": question,
        "deep": deep,
        "plan": sub_questions,
        "subq_sources": subq_sources,
        "memo_markdown": memo_md,
        "sections": sections_out,
        "sources": sources,
        "findings": findings,
        "conflicts": conflicts,
        "gaps": gaps,
        "reviewer_notes": reviewer_notes,
        "citer_notes": citer_notes,
        "grounding": grounding,
        "provider": primary,
        "providers": providers,
        "ingested": ingested,
    }
