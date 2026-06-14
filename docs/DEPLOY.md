# L.E.A.D.S. — Deployment Guide

Covers the **local run** (the current, supported path) and the **cloud
deployment path** (the production target). The app is designed to run fully with
**zero API keys** (extractive fallback), so a working deployment needs no paid
services.

---

## 1. Local run (supported)

### Prerequisites
- **Python 3.12** (ChromaDB + pydantic-core have wheels for 3.12; avoid 3.14).
- **Node 18+** for the frontend.

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env            # cp on macOS/Linux
python -m uvicorn app.main:app --port 8000
```
- On startup it idempotently ingests the public seed corpus into ChromaDB and
  prints the configured LLM providers.
- Health: `http://localhost:8000/api/health` → `{"status":"ok","phase":6,"version":"1.0.0",...}`
- Interactive API docs: `http://localhost:8000/docs`

### Frontend
```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```
For a production bundle: `npm run build` → static files in `frontend/dist/`
(serve with any static host; set `VITE_API_URL` to the backend's public URL).

### Environment variables (`backend/.env`) — ALL optional
```ini
GROQ_API_KEY=              # free-tier; first in the cascade
GEMINI_API_KEY=            # free-tier; second
ANTHROPIC_API_KEY=         # third (Claude Haiku default, for cost)
GROQ_MODEL=llama-3.3-70b-versatile
GEMINI_MODEL=gemini-2.0-flash
ANTHROPIC_MODEL=claude-3-5-haiku-latest
COURTLISTENER_API_TOKEN=   # optional; raises live case-law rate limits
FRONTEND_ORIGIN=http://localhost:5173   # CORS allow-list (comma-separated)
```
With **no keys** the app is fully functional (extractive, still-cited answers).
Add any one LLM key to enable synthesis.

---

## 2. What stays local (never deploy these)

These are gitignored at both the repo root and `backend/.gitignore`:

| Path | Contents | Why local-only |
|---|---|---|
| `backend/.env` | secrets | never commit keys |
| `backend/chroma_db/` | vector store incl. **privileged uploads** | privacy guardrail |
| `backend/uploads/` | uploaded file staging | privileged |
| `backend/.cache/` | CourtListener opinion cache | rate-limit courtesy |
| `backend/bkt_state/` | anonymous per-session mastery vectors | local user state |
| `*.log` | server logs | noise / may contain request text |

---

## 3. Cloud deployment path (production target)

The local design maps cleanly to a free-tier cloud stack.

### 3.1 Backend → Render (or any container/Python host)
- **Pin Python 3.12** (`PYTHON_VERSION=3.12.x` + a `.python-version`) — the
  default 3.14 lacks a `pydantic-core` wheel and fails the Rust build.
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Set env vars from §1 as **service secrets** (never bake keys into the image).
- Set `FRONTEND_ORIGIN` to the deployed frontend URL(s) to lock CORS.

### 3.2 Frontend → Netlify (or any static host)
- Build: `npm install && npm run build`; publish `frontend/dist/`.
- Set `VITE_API_URL` to the deployed backend URL (baked at build time).

### 3.3 Vector store → pgvector / Supabase (production target)
ChromaDB's local persistent store is perfect for local + single-instance, but
its on-disk dir is **ephemeral** on most PaaS hosts and doesn't share across
replicas. The production target is **Postgres + `pgvector`** (Supabase free
tier):
- Move the legal corpus collection to a `pgvector` table (embedding column +
  metadata: court, date, citation, jurisdiction).
- Keep **uploaded case files isolated per user** (row-level security / a
  per-user namespace) — they are privileged and must never leak across tenants.
- BKT state and memo history move from in-process to a Postgres table keyed by
  (anonymous) session/user id.
- The retrieval interface (`rag.hybrid_retrieve`) is the single seam to swap;
  BM25 can move to Postgres full-text search or a dedicated index, fused with
  pgvector cosine distance via the same RRF step.

### 3.4 Secrets & config checklist
- [ ] All API keys set as platform **secrets**, not in the repo or image.
- [ ] `FRONTEND_ORIGIN` locked to the real frontend origin(s).
- [ ] `VITE_API_URL` points at the deployed backend.
- [ ] `COURTLISTENER_API_TOKEN` set (optional) to raise case-law rate limits.
- [ ] Persistent volume (or pgvector) for the corpus if you need it to survive
      restarts; uploads remain isolated/private.
- [ ] Consider an auth layer (Supabase Auth / Clerk) before multi-user
      deployment so uploaded documents are scoped per user.

---

## 4. Smoke test after deploy

```bash
curl https://<backend-host>/api/health
# → {"status":"ok","phase":6,"version":"1.0.0","llm_providers":[...],"corpus_size":>0}

curl -X POST https://<backend-host>/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What are the FDCPA third-party location-info rules?","deep":false}'
# → cited answer (provider = a configured LLM, or "extractive (no LLM key)")
```
A green `/api/health` is necessary but **not** sufficient — always exercise a
real `/api/ask` and confirm you get grounded, cited output.
