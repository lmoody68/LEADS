# L.E.A.D.S. — MasterBuildPlan
## Legal Education & Analytical Deep-Search

**Status:** CONFIRMED SCOPE — Audit-Gated Build  
**Date:** 2026-06-13  
**Owner:** Leslie Moody  


---

## 1. Vision & Positioning

L.E.A.D.S. is a standalone AI-powered investigative research platform that bridges legal research, investigative methodology, and AI/ML engineering. It demonstrates:
- **RAG (Retrieval-Augmented Generation)** over public legal data
- **Agentic AI workflows** with LangChain
- **Adaptive learning** via Bayesian Knowledge Tracing (BKT)
- **Source credibility evaluation** using investigative rigor
- **Compliance reasoning** grounded in actual regulatory text

It is a portfolio-grade application showcasing the intersection of legal domain expertise, investigative tradecraft, and modern AI engineering.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + TS + Tailwind)        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Research    │ │ Tutor       │ │ Document    │           │
│  │ Dashboard   │ │ Mode        │ │ Analysis    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI + Python)              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ RAG Engine  │ │ Agentic     │ │ BKT Engine  │           │
│  │ (ChromaDB)  │ │ Researcher  │ │ (Adaptive)  │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Source      │ │ Compliance  │ │ Document    │           │
│  │ Scorer      │ │ Advisor     │ │ Analyzer    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Multi-Provider LLM Router (Groq → Gemini → Claude)   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                            │
│  CourtListener API │ Caselaw Access Project │ govinfo.gov  │
│  Cornell LII       │ RSS Feeds (ethical)    │ User Uploads │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Feature Modules

### 3.1 🔎 Deep-Research Engine (RAG)
**Purpose:** Natural-language queries over public legal data with cited, grounded answers.

**Capabilities:**
- Semantic search over ingested court opinions, statutes, regulations
- Query rewriting for legal specificity (e.g., "What did Smith v. Jones hold?" → structured retrieval)
- Citation extraction and formatting (Bluebook-style)
- Source linking back to original documents
- Multi-document synthesis with conflict detection

**Data Pipeline:**
1. Fetch from CourtListener API / Caselaw Access Project / govinfo.gov
2. Chunk documents with legal-aware splitting (opinion → syllabus → facts → holding → dissent)
3. Embed using `sentence-transformers/all-MiniLM-L6-v2` or legal-specific model
4. Store in ChromaDB with metadata (court, date, citation, jurisdiction)
5. Retrieve via hybrid search (semantic + keyword BM25)
6. Generate via LLM with retrieved context + citation grounding

**AI/ML Concepts Demonstrated:** RAG, vector embeddings, semantic search, hybrid retrieval, prompt engineering for citation grounding.

---

### 3.2 🤖 Agentic Research Memo
**Purpose:** Multi-step AI agent that plans, researches, synthesizes, and drafts a structured legal research memo.

**Workflow (LangChain):**
1. **Planner:** Decomposes user query into sub-questions
2. **Retriever:** For each sub-question, queries RAG engine
3. **Synthesizer:** Merges findings, resolves conflicts, identifies gaps
4. **Drafter:** Generates memo with sections: Issue, Brief Answer, Facts, Analysis, Conclusion
5. **Citer:** Ensures all claims have inline citations with source links
6. **Reviewer:** Self-checks for hallucination, missing citations, logical consistency

**Output Format:** Structured markdown memo with embedded citations and confidence scores per claim.

**AI/ML Concepts Demonstrated:** Agentic workflows, multi-step reasoning, tool use, self-reflection, structured generation.

---

### 3.3 📊 Source Credibility Scorer
**Purpose:** Apply investigative rigor to evaluate source reliability.

**Scoring Dimensions (inspired by "Golden Search Strategy"):**
| Dimension | Weight | Description |
|---|---|---|
| **Authority** | 25% | Is the source a primary authority (court, legislature) or secondary (law review, news)? |
| **Currency** | 20% | How recent? Has it been superseded or overruled? |
| **Corroboration** | 25% | Can the claim be triangulated with other independent sources? |
| **Bias/Interest** | 15% | Does the source have a stake in the outcome? |
| **Completeness** | 15% | Does the source cover the full context or omit key facts? |

**Implementation:**
- LLM-based evaluation with structured output (JSON scores + rationale)
- Cross-reference checking against multiple sources in vector store
- Shepardization-style flagging (overruled, distinguished, followed)
- Visual credibility dashboard per source

**AI/ML Concepts Demonstrated:** Structured LLM output, multi-criteria evaluation, cross-reference verification.

---

### 3.4 🎓 Investigative Methodology Tutor (BKT-Powered)
**Purpose:** Teach OSINT methodology, legal research craft, and the "Golden Search Strategy" adaptively.

**Curriculum Modules:**
1. **OSINT Fundamentals** — Open-source intelligence principles, source taxonomy, search engine operators
2. **The Golden Search Strategy** — Lead development, source triangulation, dead-end recovery
3. **Legal Research Methodology** — Case law hierarchy, statutory interpretation, Shepardizing, citators
4. **Source Evaluation** — Primary vs. secondary, bias detection, credibility assessment
5. **Compliance & Ethics** — Permissible purpose, privacy boundaries, when skip tracing is lawful

**BKT Integration (ported from N.O.V.A.S.):**
- Each learning objective has a latent knowledge state
- Quiz/assessment responses update P(known) via Bayesian update
- LLM generates personalized explanations, Socratic questioning, and remediation based on knowledge gaps
- Mastery threshold gates progression

**AI/ML Concepts Demonstrated:** Bayesian Knowledge Tracing, adaptive learning, personalized content generation, mastery-based progression.

---

### 3.5 ⚖️ Compliance & Ethics Advisor
**Purpose:** AI-grounded reasoning on when investigative methods are lawful vs. unlawful.

**RAG Corpus:**
- FCRA (Fair Credit Reporting Act) — full text + key sections
- FDCPA (Fair Debt Collection Practices Act)
- DPPA (Driver's Privacy Protection Act)
- GLBA (Gramm-Leach-Bliley Act)
- State PI licensing statutes
- Key case law interpreting these statutes

**Interaction Mode:**
- User describes a scenario (e.g., "I want to find someone's current employer for a debt collection case")
- Advisor retrieves relevant statutory text and case law
- LLM reasons through: Is there a permissible purpose? Which statute governs? What are the restrictions?
- Output: Structured legal analysis with citations, risk flags, and recommended compliant alternatives

**AI/ML Concepts Demonstrated:** Legal reasoning RAG, statutory interpretation, scenario-based reasoning, risk classification.

---

### 3.6 🧪 Practice Sandbox
**Purpose:** Synthetic skip-trace scenarios for skill-building without real PII.

**Scenario Generation:**
- LLM generates fictional investigative scenarios with realistic data artifacts (fictional court records, synthetic news articles, mock public filings)
- Learner practices the "Golden Search Strategy" on this synthetic corpus
- System evaluates methodology: Did they triangulate? Did they check source credibility? Did they identify dead ends correctly?
- BKT tracks skill mastery across scenario types

**AI/ML Concepts Demonstrated:** Synthetic data generation, skill evaluation, scenario-based learning, BKT mastery tracking.

---

### 3.7 📄 Document Analysis (Pinpoint-Style)
**Purpose:** AI-powered analysis of user-uploaded document collections.

**Capabilities:**
- Upload PDFs, images, emails, spreadsheets
- Entity extraction (people, organizations, locations, dates, legal citations)
- Relationship mapping (who is connected to whom, timeline construction)
- Full-text semantic search within the corpus
- Cross-document pattern detection
- Redaction suggestion for sensitive information

**Constraints:** Only works on documents the user lawfully possesses and uploads. No external scraping.

**AI/ML Concepts Demonstrated:** Document understanding, entity extraction, relationship extraction, semantic search over private corpora.

---

## 4. Technical Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | FastAPI + Python 3.11 | Proven pattern, async support, OpenAPI auto-docs |
| **Frontend** | React 18 + TypeScript + Tailwind CSS | Type safety, component reuse, rapid styling |
| **Vector DB** | ChromaDB | Lightweight, embeddable, good metadata filtering |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` or `BAAI/bge-large-en-v1.5` | Legal-specific or general high-quality embeddings |
| **LLM Router** | Multi-provider: Groq (Llama 3) → Gemini (Flash) → Claude (Haiku) | Free-first cascade, cost optimization |
| **Agent Framework** | LangChain + LangGraph | Proven agentic workflow orchestration |
| **BKT Engine** | Custom Python (ported from N.O.V.A.S.) | Bayesian update, mastery tracking |
| **Document Parsing** | PyPDF2, pdfplumber, Tesseract OCR | PDF text extraction, image OCR |
| **State Management** | Zustand (frontend) | Lightweight, TypeScript-friendly |
| **Auth (future)** | Supabase Auth or Clerk | Ready for multi-user deployment |

---

## 5. Data Sources & Ethics

### Legitimate Public Sources
| Source | Type | Access |
|---|---|---|
| CourtListener API | Federal/state court opinions | Free API, no scraping needed |
| Caselaw Access Project (Harvard) | Historical case law | Free bulk download |
| govinfo.gov | Federal statutes, regulations, bills | Free API |
| Cornell Legal Information Institute | Statutes, codes, regulations | Free web access |
| RSS Feeds (ethical) | Legal news, law review updates | robots.txt-respecting, rate-limited |
| User Uploads | Private documents | Only documents user lawfully possesses |

### Explicitly Excluded
- Social media scraping
- DMV record access
- People-search aggregation
- PII harvesting
- LLM training on personal data

---

## 6. Build Phases (Audit-Gated)

### Phase 0: Foundation & Scaffolding (1–2 weeks)
- [ ] Project repo setup (FastAPI + React monorepo)
- [ ] Docker dev environment
- [ ] LLM router implementation (multi-provider cascade)
- [ ] Basic vector store setup (ChromaDB)
- [ ] Document ingestion pipeline (chunking + embedding)
- [ ] Frontend shell with navigation

**Audit Gate 0:** LLM router works, documents can be ingested and queried.

### Phase 1: RAG Deep-Research Engine (2–3 weeks)
- [ ] CourtListener API integration
- [ ] Legal-aware document chunking
- [ ] Hybrid retrieval (semantic + BM25)
- [ ] Citation grounding in LLM generation
- [ ] Research dashboard UI
- [ ] Source linking and preview

**Audit Gate 1:** Can query "What did Smith v. Jones hold?" and get a cited, accurate answer.

### Phase 2: Agentic Research Memo (2–3 weeks)
- [ ] LangChain agent architecture
- [ ] Planner → Retriever → Synthesizer → Drafter → Citer → Reviewer chain
- [ ] Structured memo output with markdown
- [ ] Confidence scoring per claim
- [ ] Memo history and versioning

**Audit Gate 2:** Can generate a full research memo with inline citations from a complex query.

### Phase 3: Source Credibility & Compliance (2 weeks)
- [ ] Source Credibility Scorer implementation
- [ ] Compliance Advisor RAG corpus (FCRA/FDCPA/DPPA/GLBA)
- [ ] Scenario-based compliance reasoning
- [ ] Visual credibility dashboards

**Audit Gate 3:** Can evaluate a source's credibility and reason through a compliance scenario.

### Phase 4: BKT Tutor & Practice Sandbox (2–3 weeks)
- [ ] Port BKT engine from N.O.V.A.S.
- [ ] Curriculum content creation (OSINT, Golden Search, Legal Research)
- [ ] Adaptive quiz generation via LLM
- [ ] Synthetic scenario generation
- [ ] Mastery tracking and progression

**Audit Gate 4:** Tutor adapts to user knowledge state and generates personalized content.

### Phase 5: Document Analysis (Pinpoint-Style) (2 weeks)
- [ ] Multi-format upload (PDF, image, email)
- [ ] Entity extraction pipeline
- [ ] Relationship mapping visualization
- [ ] Semantic search within corpus
- [ ] Cross-document pattern detection

**Audit Gate 5:** Can upload a document collection and extract entities, relationships, and search semantically.

### Phase 6: Polish & Portfolio (1–2 weeks)
- [ ] UI/UX refinement
- [ ] Performance optimization
- [ ] Documentation (README, architecture diagrams)
- [ ] Demo video/script
- [ ] Deployment guide (local + cloud)

**Final Audit:** Full feature demo, code review, documentation complete.

---

## 7. AI/ML Portfolio Value

This project demonstrates:
1. **RAG Architecture** — End-to-end retrieval-augmented generation with citation grounding
2. **Agentic AI** — Multi-step reasoning workflows with LangChain
3. **Vector Embeddings & Semantic Search** — Legal-domain document retrieval
4. **Bayesian Knowledge Tracing** — Probabilistic modeling for adaptive learning
5. **Multi-Provider LLM Orchestration** — Cost-optimized, fallback-resilient routing
6. **Structured LLM Output** — JSON scoring, citation formatting, risk classification
7. **Document AI** — Entity extraction, relationship mapping, corpus analysis
8. **Ethical AI Design** — Compliance grounding, bias detection, source evaluation

---

## 8. Risk Register

| Risk | Mitigation |
|---|---|
| Hallucination in legal answers | RAG grounding + citation requirements + confidence scores |
| Outdated legal information | Freshness scoring + regular corpus updates |
| Misuse for non-compliant purposes | Explicit design excludes PII tools; compliance advisor teaches boundaries |
| API rate limits / costs | Multi-provider router + caching + local embedding |
| BKT cold start | Default priors + rapid diagnostic assessment |

---

## 9. Next Steps

1. **Confirm Phase 0 start** — I'll generate the project scaffolding
2. **Decide on project location** — New repo or within existing N.O.V.A.S. ecosystem?
3. **API key prep** — Groq, Gemini, and/or Anthropic keys for LLM router

**Ready to build Phase 0?**
