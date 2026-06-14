# L.E.A.D.S. — Architecture

This document describes the components of L.E.A.D.S. and how data flows through them.

---

## 1. High-level components

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND  (React 18 + TypeScript + Vite + Tailwind)                 │
│  • App.tsx        — tab shell + per-tab landing blurbs + guardrail    │
│                     footer                                            │
│  • views/         — ResearchView, MemoView, ComplianceView,          │
│                     DocumentView, TutorView                          │
│  • lib/api.ts     — typed fetch client (VITE_API_URL || :8000)       │
│  • components/    — AnswerBody, Sources, CredibilityPanel            │
└──────────────────────────────────────────────────────────────────────┘
                          │ REST JSON over /api/*
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│  BACKEND  (FastAPI, Python 3.12)  — app/main.py defines the routes   │
│                                                                      │
│  SERVICES (app/services/)                                            │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ rag.py           Deep-research: ensure_seed_ingested,          │ │
│  │                  hybrid_retrieve (dense+BM25+RRF), answer       │ │
│  │ query_planner.py Decompose/rewrite a query for legal retrieval │ │
│  │ courtlistener.py Live public opinions (official REST API +     │ │
│  │                  local cache, rate-limit aware)                 │ │
│  │ agent_memo.py    Planner→Retriever→Synthesizer→Drafter→Citer→   │ │
│  │                  Reviewer; reuses rag hybrid retrieval          │ │
│  │ credibility.py   5-dimension weighted source scorer            │ │
│  │ compliance.py    Statute-grounded scenario reasoning (advisory)│ │
│  │ tutor.py         Lessons / quizzes / grading                   │ │
│  │ bkt.py           Bayesian Knowledge Tracing mastery engine     │ │
│  │ sandbox.py       Synthetic (no-PII) scenarios + methodology    │ │
│  │                  evaluation → BKT updates                      │ │
│  │ casefile.py      Upload, chunk, embed, cited Q&A over an        │ │
│  │                  uploaded collection                           │ │
│  │ doc_analysis.py  Relationships / timeline / patterns /         │ │
│  │                  redaction over an uploaded collection         │ │
│  │ docparse.py      PDF/text extraction                           │ │
│  │ llm_router.py    Free-first cascade + extractive fallback      │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DATA / STATE                                                        │
│  • ChromaDB persistent store (backend/chroma_db) — legal corpus +    │
│    one private collection per uploaded case file                     │
│  • Public seed corpus (backend/app/data/seed_corpus): FDCPA, FCRA,   │
│    DPPA, GLBA                                                         │
│  • CourtListener opinion cache (backend/.cache) — local only         │
│  • BKT per-session state (backend/bkt_state) — anonymous prob vectors │
│  • In-memory memo history (last N, process-local)                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. The LLM router (free-first cascade)

`llm_router.synthesize(system, user)` is the single choke point for every LLM
call. It runs a **cost-ordered cascade** and **never crashes a request**:

```
available_providers()  →  [groq?, gemini?, anthropic?]   (keys present, in order)
        │
        ├─ groq      (llama-3.3-70b-versatile)   ──┐
        ├─ gemini    (gemini-2.0-flash)          ──┤ first non-empty success wins
        └─ anthropic (claude-3-5-haiku-latest)   ──┘
        │
        └─ all failed / no keys → (None, "extractive (no LLM key)")
```

- On a provider error/throttle (e.g. HTTP 429), it **logs** the provider, model,
  and status, then falls through to the next provider (Phase 6 observability).
- When the cascade yields `None`, the **caller** degrades to an **extractive**
  result built from the top retrieved passages + their citations. The app is
  fully functional with **zero** API keys.

---

## 3. Key data flows

### 3.1 Deep research (`POST /api/ask`)
```
question
  → query_planner: rewrite/expand for legal specificity
  → (deep=true) courtlistener: fetch live opinions → ingest into Chroma
  → rag.hybrid_retrieve:
        dense vector search  +  BM25 keyword search
        → take top-k each → Reciprocal Rank Fusion (RRF) → top passages
  → llm_router.synthesize(grounded prompt with [n] passages)
        success → cited answer + conflict detection
        fail    → EXTRACTIVE answer (top passages + citations)
  → response: { answer, sources[], conflicts, grounding, follow_ups, provider }
```

### 3.2 Agentic memo (`POST /api/memo`)
```
question
  → Planner    : decompose into sub-questions (LLM, fallback = heuristic split)
  → Retriever  : for each sub-question, rag.hybrid_retrieve (+ live case law)
  → Synthesizer: merge findings, surface conflicts/gaps
  → Drafter    : Issue / Brief Answer / Facts / Analysis / Conclusion
  → Citer      : attach inline [n] citations to REAL retrieved sources
  → Reviewer   : self-check (missing citations, consistency) → confidence
  → response: { memo_markdown, plan[], sources[], conflicts, review, provider }
```

### 3.3 Source credibility (`POST /api/credibility`)
```
source (pasted OR source_id from a prior result)
  → resolve_source: classify type from EVIDENCE
        opinion (v., reporter cite, holding language)
        statute (real U.S.C./C.F.R./§ citation)
        source  (no establishable authority → secondary/low)
  → corroborators: rag.hybrid_retrieve other corpus sources
  → llm_router score across 5 weighted dims (Authority .25, Currency .20,
        Corroboration .25, Bias/Interest .15, Completeness .15)
        fail → deterministic score (authority/currency from metadata;
                 anonymous no-citation source → secondary, authority 25)
  → + Shepardize-style HEURISTIC flag (keyword signal, NOT a real citator)
  → response: { dimensions[], weighted_total, tier, flags, corroboration, ... }
```

### 3.4 Compliance advisor (`POST /api/compliance`)
```
scenario
  → rag.hybrid_retrieve governing statutes (FDCPA/FCRA/DPPA/GLBA)
  → llm_router structured analysis (TEACHING framing; never a how-to)
        fail → deterministic, statute-grounded template (DPPA/FDCPA tripwires)
  → citations get Cornell LII deep-links (subsection-aware, e.g. /15/1681b)
  → response: { permissible_purpose, governing_statutes[], restrictions[],
                risk_flags[], compliant_alternatives[], citations[], disclaimer }
```

### 3.5 BKT tutor + sandbox (`/api/tutor/*`, `/api/sandbox/*`)
```
X-Session-Id (header or body) keys an anonymous mastery vector (15 KCs).
  lesson/quiz : llm_router generates content (fallback = curated/extractive)
  answer      : grade → bkt._bkt_update (Bayesian posterior) → mastery_after
  mastery     : per-module red/yellow/green dashboard + overall readiness %
  sandbox     : synthetic (no-PII) scenario → evaluate methodology → BKT updates
State persists to backend/bkt_state/<session>.json (gitignored, anonymous).
```

### 3.6 Document analysis (`/api/casefile/*`)
```
upload → docparse (PDF/text) → chunk → embed → Chroma collection casefile_<id>
  ask          : cited Q&A over the collection
  relationships: entities + typed relationships (LLM; fallback = proper-noun regex)
  timeline     : dated events sorted (LLM; fallback = dated-sentence regex)
  patterns     : cross-doc patterns/discrepancies (LLM; fallback = shared entities)
  redaction    : deterministic regex PII pass (ALWAYS) + optional LLM augment.
                 Cross-type digit-span dedup; phone keeps its leading "(".
All four work with NO key (deterministic fallback). Uploads stay LOCAL.
```

---

## 4. Cross-cutting design choices

- **Graceful degradation everywhere.** Every LLM step has a deterministic /
  extractive fallback so the app is fully usable with zero keys and never
  crashes on a provider error or malformed JSON.
- **Robust JSON extraction.** Each structured-output service shares an
  `_extract_json` that survives code fences and surrounding prose.
- **Local & private by default.** Privileged uploads and per-session BKT state
  live on local disk and are gitignored (repo-root and `backend/.gitignore`).
- **Input hardening.** Free-text bodies are capped at 8000 chars (HTTP 413) to
  bound cost and prompt-injection surface.
- **Citations are real.** Answers cite actual retrieved passages; compliance
  citations deep-link to Cornell LII at the correct subsection.
