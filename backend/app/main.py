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

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env from the backend root (explicit path so it works under `-m app.main`).
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.services import casefile, courtlistener, llm_router, rag  # noqa: E402

app = FastAPI(
    title="L.E.A.D.S. API",
    description="Legal Education & Analytical Deep-Search — Phase 1 (Deep-Research Engine)",
    version="0.2.0",
)

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


# --- Routes ------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "L.E.A.D.S.",
        "phase": 1,
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
