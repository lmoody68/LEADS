# L.E.A.D.S. — User Guide

**Legal Education & Analytical Deep-Search** is a local AI workbench for legal
research, learning, and document analysis. It runs on your machine: a FastAPI
backend (`:8000`) + a React frontend (`:5173`).

> **General legal information, not legal advice.** This is an educational tool and
> does not create an attorney-client relationship. Public/licensed legal data
> only · your uploaded documents stay on your machine · no web scraping, no PII.

## Run it locally

```powershell
# Backend
cd C:\Users\lesli\Documents\LEADS\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# Frontend (separate terminal)
cd C:\Users\lesli\Documents\LEADS\frontend
npm run dev      # opens http://localhost:5173
```

Open **http://localhost:5173**. The **Guide** tab (in-app) mirrors this document.

---

## 5-minute tour

1. **Research** — ask *"When may a debt collector contact a third party?"*
2. **Explain** — paste a confusing legal sentence → plain English.
3. **Compliance Advisor** — try *"A landlord wants to pull a tenant's credit report."*
4. **Data → Citator** — check *"Heintz v. Jenkins, 514 U.S. 291"*.
5. **Classifier** — click *Train*, then classify a passage.

---

## Features

### 💬 Assistant — ask anything (agentic orchestrator)
One chat box for the whole app. Ask in plain language; it **routes** your request
to the right tool (research, case brief, plain-English, compliance, citator,
related authorities, flashcards, outline, classify) and answers, showing a
**"via &lt;tool&gt;"** badge.
- **Example:** *"Is it lawful for a landlord to pull a tenant's credit report?"* →
  routes to Compliance → *Verdict: yes (FCRA § 1681b)…* Best starting point if you
  don't know which tab you need.

### 🔎 Research — Deep-Search RAG
Ask a legal question; get a **cited** answer grounded in real statutes + live
court opinions, with agreement/conflict detection.
- Keep **deep research** on to pull live CourtListener case law; off = faster,
  statute-only.
- **Example:** *"When may a debt collector contact a third party about a
  consumer's debt?"* → answer citing 15 U.S.C. § 1692b / § 1692c(b) + cases.
- It answers only from retrieved public law; if coverage is thin, it says so.

### 📝 Research Memo — Agentic
A structured written memo via Planner → Retriever → Synthesizer → Drafter →
Citer → Reviewer, with inline citations to real sources. Takes 20–60s.
- **Example:** *"Does the FDCPA apply to a law firm that only litigates
  debt-collection lawsuits?"* → memo with a sub-question plan, analysis grounded
  in § 1692a(6) + *Heintz v. Jenkins*, conclusion, and reviewer notes.
- Use when you need a work-product, not just an answer.

### 🗣️ Explain — Plain-English Transcriber + Case Brief
Two modes:
- **Plain English (for jurors):** paste jargon or a citation → everyday-language
  rewrite + glossary + analogy + bottom line.
  - **Example:** *"The appellant contends the trial court erred in granting
    summary judgment…"* → *"The person who lost says the judge decided without a
    full trial because important facts are still disputed."*
- **Case Brief (IRAC):** a citation or pasted opinion → Facts · Issue · Rule ·
  Analysis · Holding.
  - **Example:** *"Heintz v. Jenkins, 514 U.S. 291"* → full brief.

### 📚 Study Mode — learning & practice toolkit
Free, public-data study tools (general-purpose — students, paralegals,
self-represented, anyone). Five sub-modes:
- **Flashcards** — enter a topic or paste text → auto term/holding cards (tap to flip).
- **Issue-Spotter** — get a fictional fact pattern → list the issues you spot →
  *Grade my answer* (score + found/missed + coaching) or *Reveal model answer*.
- **Bluebook Cite** — paste a rough citation → formatted Bluebook (e.g.
  *"heintz v jenkins 514 us 291 1995"* → *Heintz v. Jenkins, 514 U.S. 291 (1995)*).
- **Related Authorities** — paste a holding/issue → semantic "find similar cases"
  over the corpus (the free analog of a research service's related-cases).
- **Study Outline** — a topic → a structured outline (elements, rules, exceptions).

> Not a substitute for Westlaw / LexisNexis / Bloomberg — those are paid,
> licensed services. Study Mode rebuilds their *student-facing capabilities* on
> free public data. Verify citations against the current Bluebook and primary sources.

### ⚖️ Compliance Advisor
Describe an investigative scenario → permissible-purpose verdict + governing
statutes (FCRA/FDCPA/DPPA/GLBA) + restrictions + risk flags + **lawful
alternatives**. Teaching tool — never a how-to for unlawful conduct.
- **Lawful example:** *"A landlord wants to pull a prospective tenant's credit
  report."* → permissible under FCRA § 1681b with a permissible purpose + (best
  practice) authorization + adverse-action notice.
- **Unlawful example:** *"I want to find someone's home address from DMV records
  to show up at their house."* → explains the DPPA prohibition + the lawful path.

### 📁 Document Analysis — Case-File Analyzer
Upload documents you lawfully possess (PDF/DOCX/TXT). Extracts entities, maps
relationships, builds a timeline, finds cross-document patterns, suggests PII
redactions, and answers questions over your files. **Stays local.**
- **Example:** upload a contract + two demand letters → ask *"What deadlines and
  dollar amounts are mentioned, and by whom?"* → timeline + who's-who + extracted
  facts, plus a redaction list for sensitive numbers.
- For documents you legitimately hold — never web scraping or people-search.

### 🎓 Tutor — Adaptive (BKT)
Teaches investigative-research methodology + governing law, adapting via Bayesian
Knowledge Tracing. Lessons, quizzes, a practice sandbox, and a red/yellow/green
mastery dashboard.
- **Example:** open the FCRA/permissible-purpose topic → lesson → quiz → mastery
  updates + a recommended next topic.
- Sandbox scenarios are fictional/synthetic — no real people or PII.

### 🤖 Classifier — Supervised-ML showcase
Trains a model on the corpus to tag a document's **type**
(statute/opinion/regulation/bill), shows **honest** metrics (held-out +
cross-validated), lets you test predictions, and can publish the model to
Hugging Face Hub.
- **Example:** *Train* → review accuracy/macro-F1/confusion → "Try it": *"We hold
  that the statute applies to attorneys who regularly litigate."* → predicts
  *opinion*.
- Auxiliary metadata tagger — **not legal advice**.

### 🗄️ Data — Corpus, Connectors, Citator & Datasets
The admin hub.
- **Corpus expansion** from official public APIs:
  - *CourtListener* (case law) — keyword query
  - *govinfo* (statutes) — keyword query / collection
  - *Federal Register*, *eCFR* (regulations) — keyword query
  - *Congress.gov* — a **bill number** (e.g. `HR 3221 110`)
  - *Regulations.gov* — rulemaking query
  - *OpenStates* — state-legislation keyword query (+ optional state)
  - *RECAP* — federal **dockets** keyword query
  - *Oyez* — a SCOTUS **term year** (e.g. `2019`)
  - *FBI CDE* — an **offense** (e.g. `all`) → aggregate crime stats
- **Citator** — enter a citation → is it real, how often cited, recent citing
  cases, and a treatment signal. (Real CourtListener citation network.)
- **Dataset discovery** — search public legal datasets (Hugging Face + Kaggle);
  PII datasets are flagged and refused.

---

## Connect via MCP (optional)
You can drive the whole app from an MCP client (Claude Desktop / Claude Code) —
see [`MCP_SETUP.md`](./MCP_SETUP.md).

## Notes
- The app degrades gracefully with no LLM keys (extractive, still-cited answers).
- Free LLM cascade: Groq → Cerebras → Mistral → Gemini → Anthropic.
- Local-only for now; cloud deploy steps live in `docs/DEPLOY.md` (not required).
