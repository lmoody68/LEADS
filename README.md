# L.E.A.D.S. — Legal Education & Analytical Deep-Search

A full-stack AI investigative-research platform bridging legal research,
investigative methodology, and AI/ML engineering. See `MasterBuildPlan.md` for
the full, audit-gated build plan.

## Status
**Phase 0 built** — Foundation/scaffolding + a working **RAG Deep-Research
Engine** (§3.1) and the **Document/Case-File Analyzer** (§3.7).

## Guardrails (non-negotiable)
- **Public / licensed legal data only** (seed corpus: FDCPA, FCRA, DPPA, GLBA).
- The **Case-File Analyzer works only on user-uploaded documents** — no web
  scraping, no PII harvesting.
- The **LLM router never trains on any data**.
- **Uploaded / privileged docs stay local** (`backend/chroma_db`) and are never
  published.

## Layout
```
LEADS/
  MasterBuildPlan.md     # canonical project plan
  backend/               # FastAPI + ChromaDB (RAG + case-file analyzer)
  frontend/              # React + TypeScript + Vite + Tailwind
```

## Run
- Backend: see `backend/README.md` (Python 3.12 venv -> `uvicorn app.main:app --port 8000`).
- Frontend: `cd frontend && npm install && npm run dev` (http://localhost:5173).

The app works fully with **no LLM API key** (extractive, still-cited answers).
Add a `GROQ_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` to
`backend/.env` to enable LLM synthesis.
