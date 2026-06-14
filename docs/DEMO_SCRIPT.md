# L.E.A.D.S. — Demo Script (Portfolio Walkthrough)

A tab-by-tab script for an oral/portfolio demo. For each tab: an **example query
that works**, what to **click**, and what to **say** about the AI technique on
display. Total run time ~8–12 minutes.

> **Setup:** start the backend (`uvicorn app.main:app --port 8000`) and frontend
> (`npm run dev` → http://localhost:5173). The demo works with **zero API keys**
> (extractive, still-cited answers); with a free Groq/Gemini key the answers are
> LLM-synthesized. Open `http://localhost:8000/api/health` first to show
> `phase 6 / version 1.0.0` and which providers are configured.

---

## 0. Opening (30 sec)

> "L.E.A.D.S. — Legal Education & Analytical Deep-Search — is a full-stack AI
> investigative-research platform. It demonstrates seven AI/ML techniques over
> **public legal data**, with privacy-first guardrails. Everything you'll see is
> grounded in real sources and degrades gracefully — it works even with no LLM
> API key, falling back to extractive, still-cited answers."

Point out the **header guardrail footer**: *"Public/licensed legal data only ·
Uploaded documents stay local · General legal information, not legal advice."*

---

## 1. Research tab — RAG + hybrid retrieval (2–3 min)

**Example query (works):**
> `What are the FDCPA rules on contacting third parties for location information?`

(Toggle **deep** on to also pull live CourtListener case law; off for a fast
seed-corpus-only answer.)

**Click:** type the query → **Ask**. Show the **answer**, the **Sources** panel,
and any **conflict** notes.

**What to say:**
> "This is **RAG** — Retrieval-Augmented Generation. The query is first
> *rewritten* for legal specificity, then I run **hybrid retrieval**: a **dense**
> semantic vector search *and* a **BM25** keyword search, fused with **Reciprocal
> Rank Fusion**. Hybrid matters for law because exact statutory terms — '§ 1692b',
> 'location information' — must match precisely, while semantics catch
> paraphrase. The LLM is then *constrained to the retrieved passages* and must
> cite them by number, so the answer is grounded, not hallucinated. If no LLM key
> is set, it returns the top passages + citations directly — same grounding,
> extractive."

---

## 2. Research Memo tab — agentic multi-step workflow (2 min)

**Example query (works):**
> `May a debt collector contact a debtor's neighbor to find them?`

**Click:** **Generate Memo**. Watch the **staged progress** (Planner →
Retriever → Synthesizer → Drafter → Citer → Reviewer). Show the structured memo
(Issue / Brief Answer / Facts / Analysis / Conclusion), the **sub-question
plan**, **inline citations**, and the **reviewer self-check**. Use **Copy /
Export**.

**What to say:**
> "This is an **agentic workflow** — not one prompt, but an explicit chain. A
> **Planner** decomposes the question into sub-questions; a **Retriever** runs the
> same hybrid retrieval for each; a **Synthesizer** merges findings and flags
> conflicts; a **Drafter** writes the structured memo; a **Citer** attaches inline
> citations to *real* retrieved sources; and a **Reviewer** self-checks for
> missing citations and consistency, assigning per-section confidence. It's
> transparent — every step is visible — and every claim traces back to a source."

---

## 3. Compliance Advisor tab — grounded legal reasoning + guardrail (2 min)

**Example scenario (works):**
> `A debt collector wants to find a debtor's current employer to collect on a judgment.`

**Click:** **Analyze**. Show the **permissible-purpose verdict**, **governing
statutes** (with Cornell LII links), **restrictions**, **risk flags**, and
**compliant alternatives**.

**Then demonstrate the guardrail** with a clearly-unlawful framing:
> `I want to confront my ex by pulling their address from DMV records.`

Show that the verdict is **"no"** and the tool explains *why* (DPPA) and points
to the lawful alternative — it never gives a how-to.

**What to say:**
> "This is **structured legal reasoning over a statute corpus** (FCRA, FDCPA,
> DPPA, GLBA). It retrieves the governing statutory text and produces a JSON
> analysis. The **guardrail** is the point: for an unlawful method it explains
> *why* it's impermissible and steers to the compliant path — it is a **teaching
> tool, not an operations manual**. Note the citation links deep-link to Cornell
> LII at the correct **subsection** — `/uscode/text/15/1692b`, not just `/1692`."

---

## 4. Tutor tab — Bayesian Knowledge Tracing (2 min)

**Click:** open **Tutor** → pick a knowledge component (e.g. *Source
Triangulation*) → **Lesson**, then **Quiz**. Answer a couple of questions
(get one wrong on purpose). Open the **Mastery dashboard** (red/yellow/green by
module + overall readiness %). Try the **Practice Sandbox**: **Generate
Scenario** → submit a methodology → see scored feedback + mastery updates.

**What to say:**
> "The tutor is **adaptive**, driven by **Bayesian Knowledge Tracing**. Each of
> the 15 knowledge components has a latent mastery probability. Every answer runs
> a **Bayesian posterior update** — correct raises P(known), incorrect lowers it,
> accounting for slip and guess. The dashboard turns those probabilities into a
> red/yellow/green readiness map, and the system recommends the next weakest
> skill. The sandbox generates **synthetic, no-PII** scenarios so you can practice
> the methodology safely, and your performance feeds the same BKT model."

---

## 5. Document Analysis tab — document AI + redaction (2 min)

**Setup:** upload a small text file you control, e.g. containing:
> `On March 3, 2024, Acme Corp wired funds to John Smith. SSN 123-45-6789.`
> `Contact him at (314) 555-0142. On April 5, 2024, Jane Doe at Beta LLC received it.`

**Click:** **Upload**, then run **Relationships**, **Timeline**, **Patterns**,
and **Redaction**.

**What to say:**
> "This is **document AI over a private corpus you lawfully possess** — no
> scraping, files stay local. It extracts **entities and typed relationships**
> (Acme → John Smith: transferred funds), builds a **timeline** of dated events,
> finds **cross-document patterns**, and suggests **PII redactions**. The
> redaction pass is **deterministic regex first** — so it works with zero keys —
> and the Phase-6 polish fixed two real bugs: a phone number like `(314)
> 555-0142` now keeps its leading parenthesis, and a single number is no longer
> double-reported as both 'Account number' and 'Credit card' — we dedup by the
> normalized digit-span across types. The redaction feature is privacy-*protecting*:
> it flags PII so you can remove it before sharing — it never exfiltrates it."

---

## 6. Close (30 sec)

> "To recap the AI/ML on display: **RAG**, **hybrid dense + BM25 + RRF
> retrieval**, an **agentic multi-step memo**, **Bayesian Knowledge Tracing**,
> **structured LLM output**, **document AI**, and **free-first multi-provider
> routing** — all over **public legal data**, advisory-not-operational, with no
> PII harvesting and nothing trained on personal data. It was built in seven
> audit-gated phases and runs fully even with no API keys."

---

## Appendix — quick verification (no UI)

```bash
# Health (phase 6 / v1.0.0)
curl http://localhost:8000/api/health

# Deep research (seed-corpus-only for speed)
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What are the FDCPA rules on third-party location info?","deep":false}'

# Compliance (note the Cornell subsection URLs in citations)
curl -X POST http://localhost:8000/api/compliance \
  -H "Content-Type: application/json" \
  -d '{"scenario":"A debt collector wants the debtors employer to collect a judgment"}'

# Mastery dashboard for a session
curl "http://localhost:8000/api/tutor/mastery?session_id=demo-1"
```
