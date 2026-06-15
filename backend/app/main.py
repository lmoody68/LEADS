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
import re
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env from the backend root (explicit path so it works under `-m app.main`).
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.services import (  # noqa: E402
    agent_memo,
    assistant,
    bkt,
    cache,
    casebrief,
    casefile,
    citator,
    classifier,
    compliance,
    courtlistener,
    credibility,
    dataset_discovery,
    doc_analysis,
    govdata,
    ingest,
    llm_router,
    pdf,
    plainlang,
    rag,
    reranker,
    sandbox,
    srs,
    study,
    tutor,
)

app = FastAPI(
    title="L.E.A.D.S. API",
    description=(
        "Legal Education & Analytical Deep-Search — v1.2.0 (Phase 8: expanded "
        "federal-data connectors + real citation network). Deep-research RAG, "
        "agentic research memo, source-credibility scoring with a real "
        "CourtListener citator, compliance advisor, BKT tutor + practice sandbox, "
        "document analysis, and official-API corpus expansion across case law "
        "(CourtListener), statutes (govinfo), regulations (Federal Register, "
        "eCFR), legislation (Congress.gov), and rulemaking dockets "
        "(Regulations.gov) + public legal-dataset discovery (Hugging Face Hub) — "
        "official APIs only, public legal data only, no PII / scraping / evasion."
    ),
    version="1.2.0",
)


# Hardening: cap free-text request bodies. An unbounded prompt is a cost and
# prompt-injection risk, so oversized inputs are rejected with HTTP 413 (Payload
# Too Large) rather than forwarded to the LLM router. 8000 chars comfortably
# covers a detailed scenario / question while bounding token cost.
_MAX_INPUT_CHARS = 8000


def _enforce_len(value: str, field: str) -> str:
    if value is not None and len(value) > _MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"{field} is too long ({len(value)} chars); max is {_MAX_INPUT_CHARS}.",
        )
    return value


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
    # Warm the cross-encoder reranker so the first query isn't slow (non-fatal).
    reranker.warm_up()


# --- Models ------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str
    deep: bool = True  # True = also fetch live CourtListener case law; False = seeded statutes only


class CaseAskRequest(BaseModel):
    question: str
    collection_id: str


class RedactionRequest(BaseModel):
    # Optional LLM augmentation of the always-on deterministic regex PII pass.
    use_llm: bool = True


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


# --- Phase 7: Automated Public-Legal-Data Ingestion --------------------------
class CourtListenerIngestRequest(BaseModel):
    query: str
    jurisdiction: str | None = None  # optional court id, e.g. 'ca9', 'scotus'
    limit: int = 5


class GovinfoIngestRequest(BaseModel):
    query: str | None = None       # free-text govinfo search ...
    collection: str | None = None  # ... and/or a collection code (USCODE/CFR/PLAW/BILLS)
    limit: int = 5


class DatasetIngestRequest(BaseModel):
    dataset_id: str
    source: str = "huggingface"


# --- Phase 8: Expanded federal-data connectors + citator ---------------------
class GovDataIngestRequest(BaseModel):
    query: str
    limit: int = 5
    jurisdiction: str | None = None  # OpenStates only — e.g. 'California' or 'ca'


class CitatorRequest(BaseModel):
    citation: str  # e.g. "514 U.S. 291" or "Heintz v. Jenkins, 514 U.S. 291"


class ExplainRequest(BaseModel):
    # Supply ANY one: a citation to resolve, pasted legal text, or a corpus source_id.
    citation: str | None = None
    text: str | None = None
    source_id: str | None = None


class TrainRequest(BaseModel):
    label_field: str = "doc_type"
    min_per_class: int = 20


class ClassifyRequest(BaseModel):
    text: str


# --- Phase 8: Study Mode -----------------------------------------------------
class FlashcardsRequest(BaseModel):
    topic: str | None = None
    text: str | None = None
    count: int = 8


class HypoRequest(BaseModel):
    topic: str | None = None


class HypoEvalRequest(BaseModel):
    facts: str
    answer: str


class CiteRequest(BaseModel):
    input: str


class SimilarRequest(BaseModel):
    text: str
    k: int = 6
    opinions_only: bool = True


class OutlineRequest(BaseModel):
    topic: str


class AssistantRequest(BaseModel):
    message: str
    history: list[dict] | None = None


class SrsSaveRequest(BaseModel):
    cards: list[dict]
    deck: str = "default"
    session_id: str | None = None


class SrsReviewRequest(BaseModel):
    deck: str = "default"
    card_id: str
    rating: str
    session_id: str | None = None


class ExportPdfRequest(BaseModel):
    title: str
    markdown: str
    filename: str | None = None


# --- Routes ------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "L.E.A.D.S.",
        "phase": 8,
        "version": "1.2.0",
        "llm_providers": llm_router.available_providers(),
        "corpus_size": rag.get_collection().count(),
        "courtlistener": courtlistener.availability(),
        "citator": {"available": citator.has_token()},
        "reranker": reranker.status(),
        "observability": llm_router.observability(),
        "classifier": {"trained": classifier.available()},
        "cache": cache.status(),
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
    _enforce_len(req.question, "question")
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
    _enforce_len(req.question, "question")
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
    _enforce_len(req.scenario, "scenario")
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
    _enforce_len(req.text or "", "text")
    _enforce_len(req.title or "", "title")
    _enforce_len(req.citation or "", "citation")
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


# --- Phase 5: Enhanced Document Analysis (MasterBuildPlan §3.7) --------------
# All four operate over an EXISTING uploaded collection. Results are cached per
# collection (recompute with ?refresh=true). Each LLM step degrades to a
# deterministic/extractive fallback so nothing crashes without a key.
@app.get("/api/casefile/{collection_id}/relationships")
def casefile_relationships(collection_id: str, refresh: bool = False) -> dict:
    """
    Relationship mapping: entities + typed relationships (who↔whom, how) extracted
    across the collection's documents, each with an evidence snippet + source doc.
    Falls back to deterministic proper-noun entity candidates with no LLM key.
    """
    out = doc_analysis.get_cached(collection_id, "relationships", refresh=refresh)
    return {"collection_id": collection_id, **out}


@app.get("/api/casefile/{collection_id}/timeline")
def casefile_timeline(collection_id: str, refresh: bool = False) -> dict:
    """
    Timeline construction: a sorted chronology of dated events across the docs,
    each {date, event, source_doc, snippet}. Falls back to a deterministic
    dated-sentence timeline with no LLM key.
    """
    out = doc_analysis.get_cached(collection_id, "timeline", refresh=refresh)
    return {"collection_id": collection_id, **out}


@app.get("/api/casefile/{collection_id}/patterns")
def casefile_patterns(collection_id: str, refresh: bool = False) -> dict:
    """
    Cross-document pattern / discrepancy detection: observations that span
    multiple documents, each typed 'pattern' or 'discrepancy' with supporting
    docs. Falls back to shared-entity detection with no LLM key.
    """
    out = doc_analysis.get_cached(collection_id, "patterns", refresh=refresh)
    return {"collection_id": collection_id, **out}


@app.post("/api/casefile/{collection_id}/redaction")
def casefile_redaction(collection_id: str, req: RedactionRequest | None = None) -> dict:
    """
    Redaction suggestion (PRIVACY tool): flags sensitive PII (SSN, account/routing,
    card, phone, email, DOB, EIN) so the user can redact BEFORE sharing. A
    deterministic regex pass ALWAYS runs (works with no key); an optional LLM pass
    augments it with less-structured PII (addresses, license numbers, etc.).
    """
    use_llm = req.use_llm if req else True
    out = doc_analysis.redaction(collection_id, use_llm=use_llm)
    return {"collection_id": collection_id, **out}


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


# --- Phase 7: Automated Public-Legal-Data Ingestion (MasterBuildPlan §3.8) ----
# GUARDRAIL-CRITICAL feature. Corpus expansion pulls ONLY from official public
# legal-data APIs (CourtListener v4, govinfo.gov) — honest User-Agent, sane rate
# limits, no scraping / CAPTCHA / proxy / rate-limit evasion, PUBLIC legal data
# only (no PII / people-search). See ingest.py + dataset_discovery.py docstrings.
@app.post("/api/ingest/courtlistener")
def ingest_courtlistener_route(req: CourtListenerIngestRequest) -> dict:
    """
    Bulk-ingest the top-N CourtListener opinions for a query (optionally scoped to
    a jurisdiction court id) into the shared RAG corpus. Official v4 API only;
    dedupes by citation/url (idempotent). Returns added / skipped_dupes /
    corpus_size_before / corpus_size_after.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    _enforce_len(req.query, "query")
    return ingest.ingest_courtlistener(
        req.query.strip(),
        jurisdiction=(req.jurisdiction or "").strip() or None,
        limit=req.limit,
    )


@app.post("/api/ingest/govinfo")
def ingest_govinfo_route(req: GovinfoIngestRequest) -> dict:
    """
    Ingest U.S. Code / CFR / public-law / bill text from govinfo.gov (official
    api.govinfo.gov API) by query and/or collection code. Uses a free
    api.data.gov key (GOVINFO_API_KEY/DATA_GOV_API_KEY), falling back to the
    rate-limited DEMO_KEY (noted in the response). Dedupes by package id.
    """
    if not (req.query and req.query.strip()) and not (req.collection and req.collection.strip()):
        raise HTTPException(status_code=400, detail="provide a query or a collection code")
    _enforce_len(req.query or "", "query")
    return ingest.ingest_govinfo(
        query=(req.query or "").strip() or None,
        collection=(req.collection or "").strip() or None,
        limit=req.limit,
    )


@app.get("/api/ingest/status")
def ingest_status_route() -> dict:
    """Corpus stats: total chunks, sources breakdown, and last-ingest summary."""
    return ingest.status()


@app.get("/api/datasets/discover")
def datasets_discover_route(q: str = "legal", limit: int = 12) -> dict:
    """
    Discover PUBLIC LEGAL datasets on Hugging Face Hub (+ Kaggle if creds exist) —
    official listing APIs, no scraping. Each result carries an is_pii_risk flag;
    people / PII datasets are flagged so they can be skipped.
    """
    _enforce_len(q, "q")
    return dataset_discovery.discover(query=q, limit=limit)


@app.post("/api/datasets/ingest")
def datasets_ingest_route(req: DatasetIngestRequest) -> dict:
    """
    Pull a SMALL streamed sample of a chosen PUBLIC LEGAL dataset into the corpus
    (or register its metadata if the optional 'datasets' lib is unavailable).
    REFUSES any PII-risk / people-search dataset.
    """
    if not req.dataset_id.strip():
        raise HTTPException(status_code=400, detail="dataset_id is required")
    _enforce_len(req.dataset_id, "dataset_id")
    out = dataset_discovery.ingest_dataset(req.dataset_id.strip(), source=req.source.strip() or "huggingface")
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out


# --- Phase 8: Expanded federal-data connectors (MasterBuildPlan §3.8) ---------
# Same guardrails as Phase 7: OFFICIAL public APIs only, public legal text only,
# honest User-Agent + sane rate limits + graceful 429 backoff, NO scraping /
# CAPTCHA / proxy / rate-limit evasion, NO PII / people-search. See govdata.py.
@app.post("/api/ingest/federalregister")
def ingest_federal_register_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest Federal Register documents (agency final/proposed rules + notices)
    matching a query — the actual rules implementing statutes like FDCPA/FCRA.
    KEYLESS official API. Prefers full plain text; dedupes by citation.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_federal_register(req.query.strip(), limit=req.limit)


@app.post("/api/ingest/ecfr")
def ingest_ecfr_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest Code of Federal Regulations sections matching a query via the eCFR
    search + versioner APIs (node-scoped full text). KEYLESS official API.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_ecfr(req.query.strip(), limit=req.limit)


@app.post("/api/ingest/congress")
def ingest_congress_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest Congress.gov bills matching a query (with their latest CRS summary as
    text) for legislative-history research. Uses the free api.data.gov key.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_congress(req.query.strip(), limit=req.limit)


@app.post("/api/ingest/regulations")
def ingest_regulations_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest Regulations.gov rulemaking documents matching a query. Uses the free
    api.data.gov key; page size is clamped to the API minimum of 5.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_regulations(req.query.strip(), limit=req.limit)


@app.post("/api/ingest/openstates")
def ingest_openstates_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest STATE bills matching a query via OpenStates v3 (optional jurisdiction
    scope, e.g. 'California'). Fills the state-legislation gap with real keyword
    search. Requires a free OPENSTATES_API_KEY (clear note in the response if unset).
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_openstates(
        req.query.strip(),
        jurisdiction=(req.jurisdiction or "").strip() or None,
        limit=req.limit,
    )


@app.post("/api/ingest/recap")
def ingest_recap_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest federal court DOCKETS matching a query from CourtListener's RECAP
    archive (public PACER records via the official API) for litigation research.
    Uses COURTLISTENER_API_TOKEN for higher rate limits.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_recap(req.query.strip(), limit=req.limit)


@app.post("/api/ingest/oyez")
def ingest_oyez_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest a SCOTUS term's cases (plain-language facts/question/conclusion) from
    Oyez. KEYLESS. Query = a term YEAR (e.g. '2019'); Oyez has no keyword search.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query (a SCOTUS term year) is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_oyez(req.query.strip(), limit=req.limit)


@app.post("/api/ingest/fbi_cde")
def ingest_fbi_cde_route(req: GovDataIngestRequest) -> dict:
    """
    Ingest a text summary of FBI Crime Data Explorer AGGREGATE national arrest
    statistics (query = offense slug, e.g. 'violent_crime'; optional 'YYYY-YYYY'
    range). Uses the api.data.gov key. Aggregate numbers only — no individual records.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query (an offense slug) is required")
    _enforce_len(req.query, "query")
    return govdata.ingest_fbi_cde(req.query.strip(), limit=req.limit)


# --- Phase 8: Real citation network (MasterBuildPlan §3.3 enhancement) --------
@app.post("/api/citator")
def citator_route(req: CitatorRequest) -> dict:
    """
    Look up a citation in the CourtListener citation network and return a REAL
    treatment report: validation (does it resolve to a known case?), cited-by
    count (influence), recent citing cases, and a transparent treatment signal.
    Gracefully reports 'unavailable' (so the UI can fall back) with no token /
    offline. Official CourtListener API only — public court data, no scraping.
    """
    if not req.citation.strip():
        raise HTTPException(status_code=400, detail="citation is required")
    _enforce_len(req.citation, "citation")
    return citator.treatment_for_citation(req.citation.strip())


# --- Phase 8: Explain — IRAC case brief + layman's-terms transcriber ----------
def _explain_inputs(req: "ExplainRequest") -> dict:
    if not (req.citation or req.text or req.source_id):
        raise HTTPException(status_code=400, detail="provide a citation, text, or source_id")
    _enforce_len(req.text or "", "text")
    _enforce_len(req.citation or "", "citation")
    return {
        "citation": (req.citation or "").strip() or None,
        "text": (req.text or "").strip() or None,
        "source_id": (req.source_id or "").strip() or None,
    }


@app.post("/api/brief")
def brief_route(req: ExplainRequest) -> dict:
    """
    AI Case Brief (IRAC): turn an opinion (from a citation, pasted text, or a
    corpus source_id) into facts / issue / rule / analysis / holding /
    disposition / key quotes / synopsis. Extractive fallback with no LLM key.
    """
    out = casebrief.brief(**_explain_inputs(req))
    if "error" in out:
        raise HTTPException(status_code=404, detail=out["error"])
    return out


@app.post("/api/explain")
def explain_route(req: ExplainRequest) -> dict:
    """
    Layman's-terms transcriber: translate legal jargon / a case / a statute into
    plain English for a juror — plain transcription, glossary, step-by-step, why
    it matters, an everyday analogy, and a bottom line. Built-in glossary
    fallback with no LLM key.
    """
    out = plainlang.explain(**_explain_inputs(req))
    if "error" in out:
        raise HTTPException(status_code=404, detail=out["error"])
    return out


# --- Phase 8: Auxiliary document classifier (supervised-ML showcase) ----------
# Trains a LogisticRegression head on the corpus's existing MiniLM embeddings to
# tag a document's TYPE (statute/opinion/regulation/bill). Auxiliary metadata
# tagger only — NOT legal advice, trained on PUBLIC corpus text, NO torch.
@app.get("/api/classifier/status")
def classifier_status_route() -> dict:
    """Whether a classifier is trained + its honest metrics (held-out + CV)."""
    return classifier.status()


@app.post("/api/classifier/train")
def classifier_train_route(req: TrainRequest | None = None) -> dict:
    """
    Train the auxiliary doc-type classifier on the public corpus embeddings.
    Returns honest metrics or 400 if there aren't enough labeled samples.
    """
    label_field = (req.label_field if req else "doc_type") or "doc_type"
    min_per_class = max(5, (req.min_per_class if req else 20))
    out = classifier.train(label_field=label_field, min_per_class=min_per_class)
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out


@app.post("/api/classifier/predict")
def classifier_predict_route(req: ClassifyRequest) -> dict:
    """Classify a piece of legal text by document type (auxiliary tagger)."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    _enforce_len(req.text, "text")
    out = classifier.predict(req.text.strip())
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out


# --- Phase 8: PDF export (memo / case brief) ---------------------------------
@app.post("/api/export/pdf")
def export_pdf_route(req: ExportPdfRequest) -> Response:
    """Render a title + markdown body to a downloadable PDF."""
    if not req.markdown.strip():
        raise HTTPException(status_code=400, detail="markdown is required")
    _enforce_len(req.title or "", "title")
    if len(req.markdown) > 60000:
        raise HTTPException(status_code=413, detail="document too long to export")
    data = pdf.render(req.title, req.markdown)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", (req.filename or req.title or "leads-export")).strip("_")[:60] or "leads-export"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'},
    )


# --- Phase 8: Assistant (agentic orchestrator over all tools) -----------------
@app.post("/api/assistant/chat")
def assistant_chat_route(req: AssistantRequest) -> dict:
    """
    One conversational entry point: routes a natural-language message to the
    right L.E.A.D.S. tool (research, brief, explain, compliance, citator,
    similar, flashcards, outline, classify) and returns a unified reply +
    structured data + which tool was used.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    _enforce_len(req.message, "message")
    out = assistant.chat(req.message.strip(), history=req.history)
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out


# --- Phase 8: Study Mode (general-purpose learning + practice toolkit) --------
@app.post("/api/study/flashcards")
def study_flashcards_route(req: FlashcardsRequest) -> dict:
    """Auto-generate study flashcards from a topic or pasted text."""
    _enforce_len(req.text or "", "text")
    _enforce_len(req.topic or "", "topic")
    out = study.flashcards(topic=req.topic or "", text=req.text or "", count=req.count)
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out


@app.post("/api/study/hypo")
def study_hypo_route(req: HypoRequest | None = None) -> dict:
    """Generate a fictional issue-spotter fact pattern for a doctrinal topic."""
    topic = (req.topic if req else "") or ""
    _enforce_len(topic, "topic")
    return study.hypo(topic=topic)


@app.post("/api/study/hypo/evaluate")
def study_hypo_eval_route(req: HypoEvalRequest) -> dict:
    """Grade a learner's spotted issues against a fact pattern."""
    _enforce_len(req.facts, "facts")
    _enforce_len(req.answer, "answer")
    out = study.evaluate_hypo(req.facts, req.answer)
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out


@app.post("/api/study/cite")
def study_cite_route(req: CiteRequest) -> dict:
    """Format a rough citation / case name / statute into Bluebook style."""
    if not req.input.strip():
        raise HTTPException(status_code=400, detail="input is required")
    _enforce_len(req.input, "input")
    return study.cite(req.input.strip())


@app.post("/api/study/similar")
def study_similar_route(req: SimilarRequest) -> dict:
    """Related authorities: semantic search over the corpus for similar passages/cases."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    _enforce_len(req.text, "text")
    return study.similar(req.text.strip(), k=req.k, opinions_only=req.opinions_only)


@app.post("/api/study/outline")
def study_outline_route(req: OutlineRequest) -> dict:
    """Generate a study outline for a legal topic."""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic is required")
    _enforce_len(req.topic, "topic")
    return study.outline(req.topic.strip())


# --- Phase 8: Spaced-repetition flashcard decks (per session) ----------------
@app.post("/api/study/srs/save")
def srs_save_route(
    req: SrsSaveRequest,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict:
    """Add flashcards to the session's spaced-repetition deck."""
    if not req.cards:
        raise HTTPException(status_code=400, detail="cards are required")
    sid = _session_id(x_session_id, req.session_id)
    out = srs.save_cards(sid, req.cards, deck=req.deck)
    out["session_id"] = sid
    return out


@app.get("/api/study/srs/decks")
def srs_decks_route(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session_id: str | None = None,
) -> dict:
    """List the session's decks with due counts."""
    sid = _session_id(x_session_id, session_id)
    out = srs.list_decks(sid)
    out["session_id"] = sid
    return out


@app.get("/api/study/srs/stats")
def srs_stats_route(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session_id: str | None = None,
) -> dict:
    """Study stats + streaks for the session (cards, maturity, accuracy, streak, forecast)."""
    sid = _session_id(x_session_id, session_id)
    out = srs.stats(sid)
    out["session_id"] = sid
    return out


@app.get("/api/study/srs/due")
def srs_due_route(
    deck: str = "default",
    limit: int = 20,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    session_id: str | None = None,
) -> dict:
    """Get the due cards for a deck."""
    sid = _session_id(x_session_id, session_id)
    return srs.due(sid, deck=deck, limit=limit)


@app.post("/api/study/srs/review")
def srs_review_route(
    req: SrsReviewRequest,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict:
    """Apply a review rating (again/hard/good/easy) and reschedule the card."""
    if not req.card_id.strip():
        raise HTTPException(status_code=400, detail="card_id is required")
    sid = _session_id(x_session_id, req.session_id)
    out = srs.review(sid, req.deck, req.card_id.strip(), req.rating)
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out


@app.post("/api/classifier/publish")
def classifier_publish_route() -> dict:
    """
    Publish the trained model + an honest auto-generated model card to the
    Hugging Face Hub. Requires a WRITE-scoped HF token (HF_WRITE_TOKEN). Returns
    the repo URL, or 400 with guidance if untrained / no write token / push fails.
    """
    out = classifier.publish()
    if "error" in out:
        raise HTTPException(status_code=400, detail=out["error"])
    return out
