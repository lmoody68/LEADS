"""
Study Mode (MasterBuildPlan §3 enhancement) for L.E.A.D.S. — a general-purpose
learning + practice toolkit (useful for students, paralegals, self-represented
people, or anyone learning the law). Free, public-data equivalents of common
research/study aids:

  * flashcards    — auto term/holding flashcards from a topic or pasted text
  * hypo          — generate a doctrinal fact pattern (issue-spotter) + grade
  * cite          — format a rough citation into Bluebook style
  * similar       — "related authorities": semantic search over the corpus
  * outline       — a study outline for a topic

Reuses the existing LLM router + the corpus embeddings. Every LLM step degrades
to a graceful fallback when no key is configured. GUARDRAILS: general legal
INFORMATION, not legal advice; public legal data only.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from . import llm_router, rag

try:
    from .plainlang import _GLOSSARY  # reuse the built-in legal glossary for fallbacks
except Exception:  # pragma: no cover
    _GLOSSARY = {}

_DISCLAIMER = "General legal information for study/practice — not legal advice."


def _extract_json(raw: str) -> Optional[Any]:
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*([\[{].*[\]}])\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    if not fenced:
        m = re.search(r"[\[{].*[\]}]", candidate, re.DOTALL)
        candidate = m.group(0) if m else candidate
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()] if v else []


# ===========================================================================
# Flashcards
# ===========================================================================
_FLASH_SYS = (
    "You make study FLASHCARDS for learning the law. From the provided topic or "
    "text, produce concise, accurate cards. Respond with STRICT JSON only (no "
    "markdown): {\"cards\": [{\"front\": \"term/question\", \"back\": \"clear "
    "answer/definition\"}]}. Cover the key terms, rules, and holdings. Keep each "
    "side short. Do not invent citations."
)


def flashcards(topic: str = "", text: str = "", count: int = 8) -> Dict[str, Any]:
    count = max(3, min(int(count or 8), 20))
    src = (text or "").strip() or (topic or "").strip()
    if not src:
        return {"error": "Provide a topic or some text to make flashcards from."}
    user = (
        f"Make {count} flashcards from this {'text' if text.strip() else 'topic'}:\n\n{src[:6000]}\n\n"
        "Return STRICT JSON."
    )
    raw, provider = llm_router.synthesize(_FLASH_SYS, user)
    parsed = _extract_json(raw) if raw else None
    cards: List[Dict[str, str]] = []
    if isinstance(parsed, dict):
        for c in (parsed.get("cards") or []):
            if isinstance(c, dict) and _s(c.get("front")):
                cards.append({"front": _s(c.get("front")), "back": _s(c.get("back"))})
    if cards:
        return {"cards": cards[:count], "provider": provider, "note": "", "disclaimer": _DISCLAIMER}

    # Fallback: build cards from the built-in glossary terms present in the text.
    low = src.lower()
    fb = [
        {"front": term, "back": meaning}
        for term, meaning in _GLOSSARY.items()
        if re.search(r"\b" + re.escape(term) + r"\b", low)
    ]
    return {
        "cards": fb[:count],
        "provider": provider,
        "note": "No LLM provider — showing glossary-based cards for legal terms found in the text "
        "(extractive mode). Configure an LLM key for full flashcards.",
        "disclaimer": _DISCLAIMER,
    }


# ===========================================================================
# Issue-spotter hypotheticals
# ===========================================================================
_HYPO_SYS = (
    "You are a law-school style ISSUE-SPOTTER author. For the given doctrinal "
    "area/topic, write a SHORT fictional fact pattern (no real people) that "
    "raises 2-4 legal issues, and list the model issues. Respond with STRICT JSON "
    "only: {\"area\": \"...\", \"facts\": \"the hypo (fictional)\", "
    "\"model_issues\": [{\"issue\": \"...\", \"rule\": \"...\", \"analysis\": "
    "\"how it applies to these facts\"}]}. Keep it realistic and self-contained."
)


def hypo(topic: str = "") -> Dict[str, Any]:
    topic = (topic or "").strip() or "consumer protection (FDCPA/FCRA)"
    raw, provider = llm_router.synthesize(_HYPO_SYS, f"Doctrinal area/topic: {topic}\n\nWrite the issue-spotter as STRICT JSON.")
    parsed = _extract_json(raw) if raw else None
    if not isinstance(parsed, dict) or not _s(parsed.get("facts")):
        return {
            "area": topic,
            "facts": "",
            "model_issues": [],
            "provider": provider,
            "note": "An LLM provider is required to generate practice hypotheticals.",
            "disclaimer": _DISCLAIMER,
        }
    issues = []
    for it in (parsed.get("model_issues") or []):
        if isinstance(it, dict) and _s(it.get("issue")):
            issues.append({"issue": _s(it.get("issue")), "rule": _s(it.get("rule")), "analysis": _s(it.get("analysis"))})
    return {
        "area": _s(parsed.get("area")) or topic,
        "facts": _s(parsed.get("facts")),
        "model_issues": issues,
        "provider": provider,
        "note": "",
        "disclaimer": _DISCLAIMER + " Fictional fact pattern — no real people or PII.",
    }


_HYPO_EVAL_SYS = (
    "You grade a learner's ISSUE-SPOTTING on a fact pattern. Compare their spotted "
    "issues to the merits. Respond with STRICT JSON only: {\"score_0_100\": int, "
    "\"found\": [\"issues they correctly identified\"], \"missed\": [\"important "
    "issues they missed\"], \"feedback\": \"encouraging, specific coaching\"}. Be "
    "fair and constructive."
)


def evaluate_hypo(facts: str, answer: str) -> Dict[str, Any]:
    facts = (facts or "").strip()
    answer = (answer or "").strip()
    if not facts or not answer:
        return {"error": "Provide the fact pattern and your spotted issues."}
    user = f"FACT PATTERN:\n{facts[:6000]}\n\nLEARNER'S SPOTTED ISSUES:\n{answer[:4000]}\n\nGrade as STRICT JSON."
    raw, provider = llm_router.synthesize(_HYPO_EVAL_SYS, user)
    parsed = _extract_json(raw) if raw else None
    if not isinstance(parsed, dict):
        return {"error": "An LLM provider is required to grade issue-spotting.", "provider": provider}
    try:
        score = int(parsed.get("score_0_100", 0))
    except Exception:
        score = 0
    return {
        "score_0_100": max(0, min(100, score)),
        "found": _list(parsed.get("found")),
        "missed": _list(parsed.get("missed")),
        "feedback": _s(parsed.get("feedback")),
        "provider": provider,
        "disclaimer": _DISCLAIMER,
    }


# ===========================================================================
# Bluebook citation formatter
# ===========================================================================
_CITE_SYS = (
    "You format legal citations in BLUEBOOK style. Given a rough citation, a case "
    "name, or statute details, return STRICT JSON only: {\"bluebook\": \"the "
    "formatted citation\", \"type\": \"case|statute|regulation|other\", "
    "\"components\": {\"...\": \"...\"}, \"notes\": \"any caveats or what was "
    "inferred\"}. If information is missing, format what you can and note the gaps. "
    "Do not fabricate reporters, volumes, or pages you weren't given."
)


def cite(input_text: str) -> Dict[str, Any]:
    input_text = (input_text or "").strip()
    if not input_text:
        return {"error": "Provide a citation, case name, or statute details to format."}
    raw, provider = llm_router.synthesize(_CITE_SYS, f"Format this in Bluebook style: {input_text}\n\nReturn STRICT JSON.")
    parsed = _extract_json(raw) if raw else None
    if not isinstance(parsed, dict) or not _s(parsed.get("bluebook")):
        return {
            "bluebook": input_text,
            "type": "other",
            "components": {},
            "notes": "An LLM provider is required for Bluebook formatting — showing your input unchanged.",
            "provider": provider,
            "disclaimer": _DISCLAIMER + " Verify formatting against the current Bluebook.",
        }
    comps = parsed.get("components")
    return {
        "bluebook": _s(parsed.get("bluebook")),
        "type": _s(parsed.get("type")) or "other",
        "components": comps if isinstance(comps, dict) else {},
        "notes": _s(parsed.get("notes")),
        "provider": provider,
        "disclaimer": _DISCLAIMER + " Verify formatting against the current Bluebook.",
    }


# ===========================================================================
# Related authorities — semantic "find similar cases" over the corpus
# ===========================================================================
def similar(text: str, k: int = 6, opinions_only: bool = True) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"error": "Provide text (a holding, issue, or passage) to find related authorities."}
    k = max(1, min(int(k or 6), 15))
    col = rag.get_collection()
    if col.count() == 0:
        return {"results": [], "note": "Corpus is empty — ingest some law first (Data tab)."}

    def _run(where: Optional[dict]) -> List[Dict[str, Any]]:
        try:
            res = col.query(query_texts=[text], n_results=min(k * 2, col.count()), where=where)
        except Exception:
            return []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        seen = set()
        for doc, meta, dist in zip(docs, metas, dists):
            cite = (meta or {}).get("citation", "")
            if cite in seen:
                continue
            seen.add(cite)
            out.append(
                {
                    "citation": cite,
                    "title": (meta or {}).get("source_title", ""),
                    "doc_type": (meta or {}).get("doc_type", ""),
                    "url": (meta or {}).get("url", ""),
                    "snippet": (doc or "")[:300],
                    "relevance": round(1.0 / (1.0 + float(dist)), 4),
                }
            )
            if len(out) >= k:
                break
        return out

    results = _run({"doc_type": "opinion"}) if opinions_only else _run(None)
    if not results:  # fall back to all doc types if no opinions matched
        results = _run(None)
    return {"results": results, "note": "", "disclaimer": _DISCLAIMER}


# ===========================================================================
# Study outline
# ===========================================================================
_OUTLINE_SYS = (
    "You write concise STUDY OUTLINES for legal topics. Respond with STRICT JSON "
    "only: {\"topic\": \"...\", \"sections\": [{\"heading\": \"...\", \"points\": "
    "[\"...\"]}]}. Organize logically (elements, rules, exceptions, key cases). "
    "Keep points short and accurate. Do not invent citations."
)


def outline(topic: str) -> Dict[str, Any]:
    topic = (topic or "").strip()
    if not topic:
        return {"error": "Provide a topic to outline."}
    raw, provider = llm_router.synthesize(_OUTLINE_SYS, f"Topic: {topic}\n\nWrite the study outline as STRICT JSON.")
    parsed = _extract_json(raw) if raw else None
    sections: List[Dict[str, Any]] = []
    if isinstance(parsed, dict):
        for sec in (parsed.get("sections") or []):
            if isinstance(sec, dict) and _s(sec.get("heading")):
                sections.append({"heading": _s(sec.get("heading")), "points": _list(sec.get("points"))})
    if not sections:
        return {
            "topic": topic,
            "sections": [],
            "provider": provider,
            "note": "An LLM provider is required to generate outlines.",
            "disclaimer": _DISCLAIMER,
        }
    return {"topic": _s(parsed.get("topic")) or topic, "sections": sections, "provider": provider,
            "note": "", "disclaimer": _DISCLAIMER}
