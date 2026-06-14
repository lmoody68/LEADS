"""
L.E.A.D.S. — Legal Education & Analytical Deep-Search
FastAPI backend (Phase 0: RAG Deep-Research Engine + Document/Case-File Analyzer)

=============================================================================
GUARDRAILS (NON-NEGOTIABLE — baked into the design):
  * PUBLIC / LICENSED legal data ONLY. The seed corpus is real public U.S.
    statutory text (FDCPA, FCRA, DPPA, GLBA).
  * The Case-File Analyzer works ONLY on user-uploaded documents. There is no
    web scraping and no PII harvesting anywhere in this service.
  * The LLM router makes stateless completion calls — no provider is asked to
    train on, learn from, or retain any data.
  * Uploaded / privileged documents stay LOCAL (ChromaDB persistent dir,
    ./chroma_db) and are NEVER published.
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

from app.services import casefile, llm_router, rag  # noqa: E402

app = FastAPI(
    title="L.E.A.D.S. API",
    description="Legal Education & Analytical Deep-Search — Phase 0",
    version="0.1.0",
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


class CaseAskRequest(BaseModel):
    question: str
    collection_id: str


# --- Routes ------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "L.E.A.D.S.",
        "phase": 0,
        "llm_providers": llm_router.available_providers(),
        "legal_chunks": rag.get_collection().count(),
    }


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """Cited answer over the public legal seed corpus (FDCPA/FCRA/DPPA/GLBA)."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    return rag.answer(req.question)


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
