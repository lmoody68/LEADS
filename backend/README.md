# L.E.A.D.S. — Backend (Phase 0)

**Legal Education & Analytical Deep-Search** — FastAPI backend providing a RAG
Deep-Research Engine over public U.S. legal text and a Document/Case-File
Analyzer for user-uploaded documents.

## Guardrails (non-negotiable)
- **Public / licensed legal data only.** The seed corpus is real public statutory
  text: FDCPA (15 U.S.C. §§1692b, 1692c), FCRA (15 U.S.C. §1681b), DPPA
  (18 U.S.C. §2721), GLBA (15 U.S.C. §6802).
- The **Case-File Analyzer works only on documents the user uploads** — no web
  scraping, no PII harvesting.
- The **LLM router never trains on any data** (stateless completion calls).
- **Uploaded/privileged docs stay local** (`./chroma_db`) and are never published.

## Stack
- FastAPI + Python
- **ChromaDB** embedded/persistent (`./chroma_db`) with Chroma's **default
  embedding function** (`all-MiniLM-L6-v2` via onnxruntime — no torch)
- LLM router: free-first cascade **Groq -> Gemini -> Claude**, with an
  **extractive fallback** so the app works fully with **no API key**
- Doc parsing: `pypdf` / `pdfplumber`; OCR (`pytesseract`) optional + import-guarded

## Run

> Use Python 3.12 (ChromaDB / onnxruntime have prebuilt wheels there).

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # optional: add a GROQ/GEMINI/ANTHROPIC key for LLM synthesis
uvicorn app.main:app --reload --port 8000
```

The legal seed corpus is ingested into Chroma idempotently on startup.

## Endpoints
- `GET  /api/health` — status + provider list + indexed-chunk count
- `POST /api/ask` — `{question}` -> cited answer over the legal seed corpus
- `POST /api/casefile/upload` — multipart `file` (+ optional `collection_id`) ->
  `{collection_id, chunks, entities}`
- `POST /api/casefile/ask` — `{question, collection_id}` -> cited answer over the
  uploaded collection
- `GET  /api/casefile/{collection_id}/entities` — entity outline

## With vs. without an LLM key
- **No key:** `/api/ask` returns the top retrieved statutory passages with their
  citations (extractive mode). Entity extraction falls back to deterministic
  regex for dates + legal citations.
- **With a key:** the same retrieval feeds a citation-grounded LLM synthesis, and
  entity extraction returns people/orgs/locations/dates/citations as JSON.
