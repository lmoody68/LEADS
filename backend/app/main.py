"""
L.E.A.D.S. — Legal Education & Analytical Deep-Search
FastAPI backend (Phase 1: Deep-Research Engine with live case law + hybrid
retrieval, on top of the Phase 0 Document/Case-File Analyzer)

=============================================================================
GUARDRAILS (NON-NEGOTIABLE — baked into the design):
  * PUBLIC / LICENSED legal data ONLY. The seed corpus is real public U.S.
    statutory text (FDCPA, FCRA, DPPA, GLBA). Live case law comes ONLY from the
    public CourtListener REST API (Free Law Project) — official API, no scraping.
  * The Case-File Analyzer works ONLY on user-uploaded documents. There is no
    web scraping and no PII harvesting anywhere in this service.
  * The LLM router makes stateless completion calls — no provider is asked to
    train on, learn from, or retain any data.
  * Uploaded / privileged documents stay LOCAL (ChromaDB persistent dir,
    ./chroma_db) and are NEVER published. CourtListener opinions are cached
    LOCALLY (./.cache) only to respect rate limits — never published.
=============================================================================
"""
from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env from the backend root (explicit path so it works under `-m app.main`).
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.services import (  # noqa: E402
    agent_memo,
    bkt,
    casefile,
    compliance,
    courtlistener,
    credibility,
    llm_router,
    rag,
    sandbox,
    tutor,
)

app = FastAPI(
    title="L.E.A.D.S. API",
    description=(
        "Legal Education & Analytical Deep-Search — Phase 4 "
        "(BKT Investigative-Methodology Tutor + Practice Sandbox)"
    ),
    version="0.5.0",
)


def _session_id(x_session_id: str | None, body_session_id: str | None = None) -> str:
    """
    Resolve the BKT session id: prefer the X-Session-Id header, then a body field,
    else mint a fresh one. The chosen id is echoed back to the client so the
    frontend can persist it and keep its mastery profile across requests.
    """
    sid = (x_session_id or body_session_id or "").strip()
    return sid or "sess-" + uuid.uuid4().hex[:16]

# In-memory memo history (last N). Process-local, never persisted/published —
# consistent with the "everything stays local" guardrail.
_MEMO_HISTORY: list[dict] = []
_MEMO_HISTORY_MAX = 20

_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins] + ["http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Idempotently ingest the public legal seed corpus into Chroma.
    count = rag.ensure_seed_ingested()
    print(f"[L.E.A.D.S.] Legal seed corpus ready: {count} chunks indexed.")
    providers = llm_router.available_providers()
    print(
        f"[L.E.A.D.S.] LLM providers configured: {providers or 'NONE (extractive fallback active)'}"
    )


# --- Models ------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str
    deep: bool = True  # True = also fetch live CourtListener case law; False = seeded statutes only


class CaseAskRequest(BaseModel):
    question: str
    collection_id: str


class MemoRequest(BaseModel):
    question: str
    deep: bool = True  # True = also pull live CourtListener case law per sub-question


class ComplianceRequest(BaseModel):
    scenario: str


class CredibilityRequest(BaseModel):
    # Either reference a source by id (chunk_id from a prior result) ...
    source_id: str | None = None
    # ... or paste the source directly.
    title: str | None = None
    citation: str | None = None
    text: str | None = None


# --- Phase 4: BKT Tutor + Practice Sandbox -----------------------------------
class KcRequest(BaseModel):
    kc: str
    session_id: str | None = None  # optional fallback if no X-Session-Id header


class AnswerRequest(BaseModel):
    kc: str
    question_id: str
    answer: object  # int (mc option index) or str (short answer)
    session_id: str | None = None


class ScenarioRequest(BaseModel):
    session_id: str | None = None


class EvaluateRequest(BaseModel):
    scenario_id: str
    approach: str
    session_id: str | None = None


# --- Routes ------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "L.E.A.D.S.",
        "phase": 4,
        "version": "0.5.0",
        "llm_providers": llm_router.available_providers(),
        "corpus_size": rag.get_collection().count(),
        "courtlistener": courtlistener.availability(),
    }


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """
    Deep-research answer. The pipeline plans the query, (optionally) fetches live
    CourtListener case law, retrieves over statutes + opinions via hybrid
    dense+BM25+RRF search, and synthesizes a citation-grounded answer with
    conflict detection, grounding, and follow-up suggestions.

    deep=True (default): include live case law. deep=False: seeded statutes only.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    return rag.answer(req.question, deep=req.deep)


@app.post("/api/memo")
def memo(req: MemoRequest) -> dict:
    """
    Agentic Research Memo (MasterBuildPlan §3.2). Runs the multi-step agent —
    Planner -> Retriever -> Synthesizer -> Drafter -> Citer -> Reviewer — and
    returns a structured legal research memo with inline citations to REAL
    retrieved sources (seeded statutes + live CourtListener opinions), the
    sub-question plan, conflicts, and a reviewer self-check.

    NOTE: this makes several LLM + retrieval calls and can legitimately take
    20-60s (especially with deep=True pulling live case law per sub-question).
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    result = agent_memo.generate_memo(req.question, deep=req.deep)
    # Record a compact entry in the in-memory history.
    _MEMO_HISTORY.append(
        {
            "question": result.get("question", ""),
            "deep": result.get("deep", req.deep),
            "plan": result.get("plan", []),
            "provider": result.get("provider", ""),
            "n_sources": len(result.get("sources", [])),
            "memo_markdown": result.get("memo_markdown", ""),
        }
    )
    if len(_MEMO_HISTORY) > _MEMO_HISTORY_MAX:
        del _MEMO_HISTORY[: len(_MEMO_HISTORY) - _MEMO_HISTORY_MAX]
    return result


@app.get("/api/memo/history")
def memo_history(limit: int = 10) -> dict:
    """Return the last N memo requests (in-memory, newest last)."""
    limit = max(1, min(limit, _MEMO_HISTORY_MAX))
    return {"history": _MEMO_HISTORY[-limit:], "total": len(_MEMO_HISTORY)}


@app.post("/api/compliance")
def compliance_analyze(req: ComplianceRequest) -> dict:
    """
    Compliance & Ethics Advisor (MasterBuildPlan §3.5). TEACHING/ADVISORY ONLY:
    given a user-described investigative scenario, retrieve the governing
    statutory text (FDCPA/FCRA/DPPA/GLBA) from the seeded corpus and produce a
    STRUCTURED legal analysis — permissible-purpose verdict, governing statutes,
    restrictions, risk flags, and COMPLIANT alternatives, with citations and a
    'general legal information, not legal advice' disclaimer.

    GUARDRAIL: for an unlawful scenario it explains WHY the method is
    impermissible and steers to the lawful alternative — it is NEVER a how-to for
    unlawful skip tracing / PII gathering.
    """
    if not req.scenario.strip():
        raise HTTPException(status_code=400, detail="scenario is required")
    return compliance.analyze(req.scenario)


@app.post("/api/credibility")
def credibility_score(req: CredibilityRequest) -> dict:
    """
    Source Credibility Scorer (MasterBuildPlan §3.3). Scores a source across the
    five weighted dimensions (Authority 25 / Currency 20 / Corroboration 25 /
    Bias-Interest 15 / Completeness 15) → weighted total + tier + flags +
    corroboration (agree/conflict against other corpus sources) + a clearly-
    labeled Shepardize-style HEURISTIC.

    Provide either a `source_id` (chunk_id from a prior result) OR a pasted
    {title, citation, text}.
    """
    if not (req.source_id or req.title or req.citation or req.text):
        raise HTTPException(
            status_code=400,
            detail="provide a source_id, or a title/citation/text to score",
        )
    return credibility.score(
        source_id=req.source_id,
        title=req.title,
        citation=req.citation,
        text=req.text,
    )


@app.post("/api/casefile/upload")
async def casefile_upload(
    file: UploadFile = File(...),
    collection_id: str | None = Form(default=None),
) -> dict:
    """Upload a user-possessed document -> {collection_id, chunks, entities}."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    return casefile.ingest_upload(file.filename or "upload", data, collection_id)


@app.post("/api/casefile/ask")
def casefile_ask(req: CaseAskRequest) -> dict:
    """Cited answer over a single uploaded case-file collection."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    if not req.collection_id.strip():
        raise HTTPException(status_code=400, detail="collection_id is required")
    return casefile.answer(req.question, req.collection_id)


@app.get("/api/casefile/{collection_id}/entities")
def casefile_entities(collection_id: str) -> dict:
    """Entity outline for an uploaded collection."""
    return {"collection_id": collection_id, "entities": casefile.get_entities(collection_id)}


# --- Phase 4: BKT Investigative-Methodology Tutor (MasterBuildPlan §3.4) ------
@app.get("/api/tutor/curriculum")
def tutor_curriculum() -> dict:
    """The 5 curriculum modules and their knowledge components (no session state)."""
    return tutor.get_curriculum()


@app.post("/api/tutor/lesson")
def tutor_lesson(req: KcRequest) -> dict:
    """Generate an LLM lesson for one knowledge component (free-first router)."""
    if not req.kc.strip():
        raise HTTPException(status_code=400, detail="kc is required")
    out = tutor.generate_lesson(req.kc.strip())
    if "error" in out:
        raise HTTPException(status_code=404, detail=out["error"])
    return out


@app.post("/api/tutor/quiz")
def tutor_quiz(req: KcRequest) -> dict:
    """Generate a quiz (mc + short) for a KC. Answer keys stay server-side."""
    if not req.kc.strip():
        raise HTTPException(status_code=400, detail="kc is required")
    out = tutor.generate_quiz(req.kc.strip())
    if "error" in out:
        raise HTTPException(status_code=404, detail=out["error"])
    return out


@app.post("/api/tutor/answer")
def tutor_answer(
    req: AnswerRequest,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict:
    """
    Grade one answer, run the Bayesian Knowledge Tracing update, and return
    {correct, feedback, mastery_before, mastery_after, recommended_next}.
    """
    if not req.kc.strip() or not req.question_id.strip():
        raise HTTPException(status_code=400, detail="kc and question_id are required")
    sid = _session_id(x_session_id, req.session_id)
    out = tutor.grade(sid, req.kc.strip(), req.question_id.strip(), req.answer)
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    out["session_id"] = sid
    return out


@app.get("/api/tutor/mastery")
def tutor_mastery(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session_id: str | None = None,
) -> dict:
    """Per-session BKT mastery profile (red/yellow/green by KC + overall %)."""
    sid = _session_id(x_session_id, session_id)
    profile = bkt.get_profile(sid)
    profile["recommended_next"] = bkt.recommend_next(sid)
    return profile


# --- Phase 4: Practice Sandbox (MasterBuildPlan §3.6) ------------------------
@app.post("/api/sandbox/scenario")
def sandbox_scenario(
    req: ScenarioRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict:
    """
    Generate a CLEARLY-SYNTHETIC, FICTIONAL investigative scenario (no real PII)
    for the learner to practice the Golden Search Strategy.
    """
    sid = _session_id(x_session_id, req.session_id if req else None)
    out = sandbox.generate_scenario()
    out["session_id"] = sid
    return out


@app.post("/api/sandbox/evaluate")
def sandbox_evaluate(
    req: EvaluateRequest,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict:
    """
    Evaluate the learner's submitted research APPROACH (methodology) against a
    synthetic scenario → scored feedback + per-KC BKT mastery updates.
    """
    if not req.scenario_id.strip():
        raise HTTPException(status_code=400, detail="scenario_id is required")
    if not req.approach.strip():
        raise HTTPException(status_code=400, detail="approach is required")
    sid = _session_id(x_session_id, req.session_id)
    out = sandbox.evaluate(sid, req.scenario_id.strip(), req.approach)
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    out["session_id"] = sid
    return out
