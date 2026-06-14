# L.E.A.D.S. — Legal Education & Analytical Deep-Search

**A full-stack, AI-powered investigative-research platform that bridges legal research, investigative methodology, and modern AI/ML engineering.**

L.E.A.D.S. lets you ask natural-language legal questions and get **cited, grounded** answers over real public legal data; drafts a **structured research memo** with a transparent multi-step agent; scores how **credible** a source is with investigative rigor; reasons about **compliance** (FCRA / FDCPA / DPPA / GLBA) for a described scenario; **teaches** investigative methodology adaptively with Bayesian Knowledge Tracing; and analyzes **documents you lawfully possess** (entities, relationships, timelines, patterns, PII redaction).

It is a **portfolio-grade** application built to demonstrate the intersection of legal-domain knowledge, investigative tradecraft, and AI engineering — RAG, hybrid retrieval, agentic workflows, BKT, structured LLM output, document AI, and free-first multi-provider routing — all with **privacy-first guardrails** baked in.

> **Version 1.0.0** · Built in 7 audit-gated phases (0–6). See `MasterBuildPlan.md` for the full plan and `docs/` for architecture, demo, and deploy guides.

---

## What it does (5 feature tabs)

| Tab | Module (MasterBuildPlan) | What it does |
|---|---|---|
| **Research** | §3.1 Deep-Research Engine (RAG) | NL query → hybrid (dense + BM25 + RRF) retrieval over public statutes **and live CourtListener case law** → grounded, **cited** answer with conflict detection. |
| **Research Memo** | §3.2 Agentic Research Memo | A transparent multi-step agent — **Planner → Retriever → Synthesizer → Drafter → Citer → Reviewer** — drafts a structured memo (Issue / Brief Answer / Facts / Analysis / Conclusion) with inline citations to real sources, per-section confidence, conflicts/gaps, and a reviewer self-check. |
| **Compliance Advisor** | §3.5 Compliance & Ethics Advisor | **Teaching/advisory only.** Describe a scenario; get a statute-grounded analysis: permissible-purpose verdict, governing statutes, restrictions, risk flags, and **lawful alternatives**. For an unlawful method it explains *why* and steers to the compliant path — never a how-to. |
| **Document Analysis** | §3.3 Credibility + §3.7 Document AI | Score a source's credibility across 5 weighted dimensions; upload documents you lawfully possess for entity + **relationship mapping**, **timeline**, **cross-document patterns**, and **PII redaction suggestions**. Files stay local. |
| **Tutor** | §3.4 BKT Tutor + §3.6 Sandbox | Adaptive investigative-methodology tutor powered by **Bayesian Knowledge Tracing** — lessons, quizzes, a synthetic practice sandbox, and a red/yellow/green **mastery dashboard**. |

---

## Architecture (text diagram)

```
┌──────────────────────────────────────────────────────────────────────┐
│        FRONTEND — React 18 + TypeScript + Vite + Tailwind            │
│  Research │ Research Memo │ Compliance │ Document Analysis │ Tutor    │
└──────────────────────────────────────────────────────────────────────┘
                                  │  REST (/api/*)
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 BACKEND — FastAPI (Python 3.12)                      │
│                                                                      │
│  rag.py            Deep-research: query plan → hybrid retrieve       │
│                    (dense + BM25 + RRF) → grounded, cited synthesis  │
│  agent_memo.py     Planner→Retriever→Synthesizer→Drafter→Citer→Review│
│  credibility.py    5-dimension weighted source scorer               │
│  compliance.py     Statute-grounded scenario reasoning (advisory)   │
│  tutor.py + bkt.py BKT mastery engine + adaptive lessons/quizzes    │
│  sandbox.py        Synthetic (no-PII) practice scenarios + eval     │
│  casefile.py +     Document AI over USER-UPLOADED collections:      │
│  doc_analysis.py     entities, relationships, timeline, patterns,   │
│                      PII redaction (deterministic regex + LLM)      │
│                                                                      │
│  llm_router.py     FREE-FIRST cascade: Groq → Gemini → Claude(Haiku)│
│                    → extractive fallback (works with ZERO keys)     │
│  courtlistener.py  Live public case law (official REST API)         │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DATA  · ChromaDB vector store (local) — seed statutes + opinions   │
│        · Public seed corpus: FDCPA, FCRA, DPPA, GLBA                 │
│        · CourtListener API (live opinions, cached locally)          │
│        · BKT per-session mastery state (anonymous, local)           │
│        · User uploads (privileged — local only, never published)    │
└──────────────────────────────────────────────────────────────────────┘
```

See **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** for components and full data flow.

---

## The 7 build phases

| Phase | Delivered |
|---|---|
| **0 — Foundation** | FastAPI + React scaffolding, free-first LLM router, ChromaDB store, ingestion pipeline, Case-File Analyzer (§3.7 base). |
| **1 — RAG Deep-Research** | Live CourtListener case law, legal-aware chunking, **hybrid dense + BM25 + RRF** retrieval, citation-grounded synthesis with conflict detection. |
| **2 — Agentic Research Memo** | Transparent 6-step agent producing a structured, cited memo with per-section confidence + reviewer self-check. |
| **3 — Credibility + Compliance** | 5-dimension weighted source scorer; statute-grounded compliance advisor (FCRA/FDCPA/DPPA/GLBA). |
| **4 — BKT Tutor + Sandbox** | Bayesian Knowledge Tracing engine (ported from N.O.V.A.S.), adaptive lessons/quizzes, synthetic practice sandbox, mastery dashboard. |
| **5 — Document Analysis** | Relationship mapping, timeline construction, cross-document pattern/discrepancy detection, PII redaction suggestions. |
| **6 — Polish & Portfolio** | Audit-fix sweep, input hardening, UI/UX polish, and these portfolio docs. |

---

## AI/ML concepts demonstrated

- **RAG (Retrieval-Augmented Generation)** — citation-grounded answers over a real legal corpus; the LLM is constrained to retrieved passages and must cite them.
- **Hybrid retrieval — dense + BM25 + RRF** — semantic embeddings *and* keyword BM25, fused with **Reciprocal Rank Fusion** for robust ranking on legal text (where exact statutory terms matter).
- **Agentic, multi-step workflow** — an explicit Planner → Retriever → Synthesizer → Drafter → Citer → Reviewer chain with self-reflection, rather than a single prompt.
- **Bayesian Knowledge Tracing (BKT)** — a latent per-skill mastery probability updated by Bayesian posterior on each correct/incorrect observation; drives adaptive content + a mastery dashboard.
- **Structured LLM output** — JSON-schema'd scoring (credibility), structured compliance analysis, quiz generation — each with a robust `_extract_json` and a deterministic fallback so malformed output never crashes the app.
- **Document AI** — entity extraction, relationship mapping, timeline construction, cross-document pattern detection, and regex+LLM PII redaction over private corpora.
- **Free-first multi-provider routing** — a cost-optimized cascade (Groq → Gemini → Claude Haiku) that **degrades to an extractive, still-cited answer with zero API keys**.

---

## Ethics & guardrails (non-negotiable)

- **Public / licensed legal data only.** Seed corpus is real public U.S. statutory text (FDCPA, FCRA, DPPA, GLBA); live case law comes only from the **official CourtListener REST API** (Free Law Project) — no scraping.
- **Advisory, not operational.** The Compliance Advisor is a **teaching tool**: for an unlawful method it explains *why* it is impermissible and points to the lawful alternative — it never produces a how-to for unlawful skip tracing or PII gathering.
- **No PII harvesting.** Document analysis works **only on documents the user lawfully possesses and uploads.** There is no web scraping and no external PII collection anywhere in the service.
- **No model trained on personal data.** LLM calls are **stateless completions** — no provider is asked to train on, retain, or learn from any data.
- **Privacy-first.** Uploaded/privileged documents and per-session BKT state stay **local** (`backend/chroma_db`, `backend/bkt_state/`) and are never published (both are gitignored). The redaction feature is privacy-*protecting* — it flags PII so you can remove it before sharing; it never exfiltrates it.
- **Input hardening.** Free-text request bodies are length-capped (8000 chars → HTTP 413) to bound cost and prompt-injection surface.
- **Not legal advice.** Output is general legal *information*; a disclaimer is always attached (including in the keyless fallback path).

---

## Data sources

| Source | Type | Access |
|---|---|---|
| **CourtListener API** (Free Law Project) | Federal/state court opinions | Free REST API. **Optional** `COURTLISTENER_API_TOKEN` raises rate limits; **without** a token it still works (anonymous, heavily rate-limited; on HTTP 429 the pipeline gracefully falls back to the seeded statute corpus). |
| **Public statute seed corpus** | FDCPA, FCRA, DPPA, GLBA full text | Bundled in `backend/app/data/seed_corpus/`. |
| **Caselaw Access Project / govinfo.gov / Cornell LII** | Statutes, regs, historical case law | Referenced for citation URLs (Cornell LII deep-links). |
| **User uploads** | Private documents | Local only; only documents the user lawfully possesses. |

**Free token note:** every external data source here is free. The only optional token (`COURTLISTENER_API_TOKEN`) just raises rate limits — the app is fully functional without it, and fully functional with **zero LLM keys** (extractive fallback).

---

## How to run

### Backend (FastAPI, Python 3.12)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env            # then fill in any keys you have (all optional)
python -m uvicorn app.main:app --port 8000
```
Health check: `http://localhost:8000/api/health` → `{"status":"ok","phase":6,"version":"1.0.0",...}`
API docs (Swagger): `http://localhost:8000/docs`

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

### `.env` keys (ALL optional — the app runs with none)
```ini
GROQ_API_KEY=          # free-tier; first in the cascade
GEMINI_API_KEY=        # free-tier; second
ANTHROPIC_API_KEY=     # third (Claude Haiku by default, for cost)
COURTLISTENER_API_TOKEN=   # optional; raises case-law rate limits
```
With **no keys**, every feature still works via the extractive, still-cited fallback. Add any one key to enable LLM synthesis.

See **[`docs/DEPLOY.md`](docs/DEPLOY.md)** for the cloud deployment path.

---

## Repo layout
```
LEADS/
  MasterBuildPlan.md         # canonical, audit-gated build plan
  README.md                  # this file
  docs/
    ARCHITECTURE.md          # components + data flow
    DEMO_SCRIPT.md           # tab-by-tab portfolio walkthrough
    DEPLOY.md                # local run + cloud deployment guide
  backend/                   # FastAPI + ChromaDB
    app/
      main.py                # routes
      services/              # rag, agent_memo, credibility, compliance,
                             # tutor, bkt, sandbox, casefile, doc_analysis,
                             # courtlistener, llm_router
      data/seed_corpus/      # public statute seed corpus
  frontend/                  # React + TypeScript + Vite + Tailwind
    src/views/               # Research, Memo, Compliance, Document, Tutor
```
