import { useState } from "react";

type Section = {
  id: string;
  icon: string;
  tab: string;
  title: string;
  what: string;
  steps: string[];
  example: { label: string; input: string; result: string };
  note?: string;
};

const SECTIONS: Section[] = [
  {
    id: "research",
    icon: "🔎",
    tab: "Research",
    title: "Deep-Search Research",
    what:
      "Ask a legal question in plain English and get a cited answer grounded in real statutes + live court opinions. It plans your query, retrieves with hybrid search (semantic + keyword) + a re-ranker, and flags where sources agree or conflict.",
    steps: [
      "Type a question.",
      "Leave 'deep research' ON to also pull live CourtListener case law; turn it OFF for a faster statute-only answer.",
      "Read the answer — every claim is cited [n; citation]. Check the Sources and the agreement/conflict notes.",
      "Use a follow-up suggestion to dig deeper.",
    ],
    example: {
      label: "Debt-collection question",
      input: "When may a debt collector contact a third party about a consumer's debt?",
      result:
        "A cited answer anchored in 15 U.S.C. § 1692b and § 1692c(b), plus any retrieved cases interpreting them — with a note if a case limits the statute.",
    },
    note: "It answers ONLY from retrieved public law. If the corpus doesn't cover something, it says so instead of guessing.",
  },
  {
    id: "memo",
    icon: "📝",
    tab: "Research Memo",
    title: "Agentic Research Memo",
    what:
      "Generates a structured written memo (issue → analysis → conclusion) using a multi-step agent: Planner → Retriever → Synthesizer → Drafter → Citer → Reviewer. Inline citations point to real retrieved sources.",
    steps: [
      "Enter a research question (broader than a single fact works well).",
      "Keep 'deep' on to pull live case law per sub-question.",
      "Wait 20–60s — it runs several retrieval + LLM steps.",
      "Review the sub-question plan, the drafted sections, the sources, and the Reviewer's self-check.",
    ],
    example: {
      label: "Scope-of-statute memo",
      input: "Does the FDCPA apply to a law firm that does nothing but litigate debt-collection lawsuits?",
      result:
        "A memo with a sub-question plan, an analysis grounded in § 1692a(6) and Heintz v. Jenkins, a conclusion, and reviewer notes flagging any gaps.",
    },
    note: "Use this when you need a work-product to read or share, not just a quick answer.",
  },
  {
    id: "explain",
    icon: "🗣️",
    tab: "Explain",
    title: "Plain-English Transcriber + Case Brief",
    what:
      "Two modes. 'Plain English (for jurors)' rewrites legal jargon into everyday language with a glossary, an analogy, and a bottom line. 'Case Brief (IRAC)' turns an opinion into Facts · Issue · Rule · Analysis · Holding.",
    steps: [
      "Pick a mode: Plain English or Case Brief (IRAC).",
      "Paste legal text/jargon, OR enter a case citation to pull the opinion.",
      "Click Transcribe / Brief it.",
      "Plain mode → read the rewrite + glossary; Brief mode → read the structured brief.",
    ],
    example: {
      label: "Decode a confusing sentence",
      input:
        "Plain English mode: 'The appellant contends the trial court erred in granting summary judgment, arguing genuine issues of material fact preclude judgment as a matter of law.'",
      result:
        "“The person who lost says the judge made a mistake by deciding without a full trial, because important facts are still disputed.” + a glossary of every term.",
    },
    note: "Great for prepping a juror, a student, or a non-lawyer. Case Brief works from a citation like 'Heintz v. Jenkins, 514 U.S. 291'.",
  },
  {
    id: "compliance",
    icon: "⚖️",
    tab: "Compliance Advisor",
    title: "Compliance & Ethics Advisor",
    what:
      "Describe an investigative scenario and get a teaching analysis: a permissible-purpose verdict, the governing statutes (FCRA/FDCPA/DPPA/GLBA), restrictions, risk flags, and LAWFUL alternatives. It explains boundaries — never a how-to for unlawful conduct.",
    steps: [
      "Describe what someone wants to do and why.",
      "Click Analyze.",
      "Read the verdict (yes / no / depends), the statutes it cites, the restrictions, and the compliant path.",
    ],
    example: {
      label: "Tenant screening",
      input: "A landlord wants to pull a prospective tenant's consumer credit report before renting to them.",
      result:
        "Verdict: permissible under FCRA § 1681b for a tenancy decision — IF you have a permissible purpose + (best practice) the applicant's authorization, and you give an adverse-action notice if you deny based on it.",
    },
    note: "Try an unlawful one too (e.g., using DMV records to find someone's home address) — it explains the DPPA prohibition and the lawful alternative.",
  },
  {
    id: "document",
    icon: "📁",
    tab: "Document Analysis",
    title: "Case-File Analyzer (your own documents)",
    what:
      "Upload documents you lawfully possess (PDF / DOCX / TXT). It extracts people/orgs/dates, maps relationships, builds a timeline, finds cross-document patterns, suggests PII redactions, and answers questions over YOUR files. Everything stays on your machine.",
    steps: [
      "Upload one or more documents.",
      "Review the extracted entities.",
      "Open Relationships, Timeline, and Patterns for cross-document insight.",
      "Run Redaction to flag SSNs / account numbers / etc. before you share a file.",
      "Ask a question about the documents in the box.",
    ],
    example: {
      label: "Demand-letter packet",
      input: "Upload a contract + two demand letters, then ask: 'What deadlines and dollar amounts are mentioned, and by whom?'",
      result:
        "A timeline of the letters, a who's-who of parties, the extracted deadlines/amounts with the source document, and a redaction list for any sensitive numbers.",
    },
    note: "This is for documents you legitimately hold — it never scrapes the web or gathers data on people.",
  },
  {
    id: "tutor",
    icon: "🎓",
    tab: "Tutor",
    title: "Adaptive Methodology Tutor (BKT)",
    what:
      "Teaches investigative-research methodology + the governing law, and adapts to you using Bayesian Knowledge Tracing. Lessons, quizzes, a practice sandbox, and a red/yellow/green mastery dashboard.",
    steps: [
      "Pick a knowledge component (topic) from the curriculum.",
      "Read the lesson, then take the quiz.",
      "Your mastery updates (red → yellow → green) and it recommends what to study next.",
      "Try the Practice Sandbox: get a synthetic scenario, submit your research approach, get scored feedback.",
    ],
    example: {
      label: "Learn permissible purpose",
      input: "Open the FCRA/permissible-purpose topic → read the lesson → answer the quiz.",
      result:
        "Graded feedback, a mastery bump on that concept, and a 'recommended next' topic to keep you progressing.",
    },
    note: "The sandbox scenarios are fictional and synthetic — no real people or PII.",
  },
  {
    id: "classifier",
    icon: "🤖",
    tab: "Classifier",
    title: "Auxiliary ML Classifier (supervised-ML showcase)",
    what:
      "Trains a small machine-learning model on the corpus to tag a document's TYPE (statute/opinion/regulation/bill), shows honest metrics (held-out + cross-validated), lets you test predictions, and can publish the model to Hugging Face Hub.",
    steps: [
      "Click 'Train classifier' — it learns from the current corpus in a few seconds.",
      "Read the metrics: accuracy, macro-F1, the per-class table, and the confusion matrix.",
      "In 'Try it', paste any passage to see the predicted type + confidence bars.",
      "Optionally click '🤗 Publish to HF Hub' to publish the model + an auto-generated model card.",
    ],
    example: {
      label: "Classify a passage",
      input: "Try it: 'We hold that the statute applies to attorneys who regularly litigate.'",
      result: "Predicts 'opinion' with high confidence, and shows the probability for each class.",
    },
    note: "This is an auxiliary metadata tagger — it labels document type, NOT legal advice.",
  },
  {
    id: "data",
    icon: "🗄️",
    tab: "Data",
    title: "Corpus, Connectors, Citator & Datasets",
    what:
      "The admin hub. Grow the knowledge base from official public APIs (case law, statutes, regulations, legislation, dockets, SCOTUS summaries, crime stats), validate a citation against the real CourtListener citation network, and discover public legal datasets.",
    steps: [
      "Corpus expansion: pick a source, type a query (or a bill/term/offense for the specialized ones), set a limit, Ingest.",
      "Citator: enter a citation to see if it's real, how often it's been cited, and recent citing cases.",
      "Dataset discovery: search public legal datasets (Hugging Face + Kaggle); PII datasets are flagged and refused.",
      "Watch the Corpus stats update as you add sources.",
    ],
    example: {
      label: "Add case law + check a cite",
      input:
        "Source 'CourtListener (case law)', query 'FDCPA attorney debt collection', Ingest. Then Citator → 'Heintz v. Jenkins, 514 U.S. 291'.",
      result:
        "New opinions added to the corpus; the citator shows Heintz is validated and heavily cited, with recent citing opinions.",
    },
    note: "Source notes: Congress.gov takes a bill number ('HR 3221 110'), Oyez takes a term year ('2019'), FBI CDE takes an offense ('all'). Official APIs only — no scraping, no PII.",
  },
];

export default function GuideView() {
  const [open, setOpen] = useState<string>("research");

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">User Guide</h2>
        <p className="text-sm text-slate-500">
          L.E.A.D.S. (Legal Education &amp; Analytical Deep-Search) is a local AI workbench for
          legal research, learning, and document analysis. Click any feature below for what it does,
          how to use it, and a real example you can copy.
        </p>
      </div>

      {/* Quick start */}
      <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 text-sm">
        <h3 className="font-semibold text-indigo-800">Start here (5-minute tour)</h3>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-slate-700">
          <li>
            <strong>Research</strong> — ask: <em>"When may a debt collector contact a third party?"</em>
          </li>
          <li>
            <strong>Explain</strong> — paste a confusing legal sentence and get plain English.
          </li>
          <li>
            <strong>Compliance Advisor</strong> — try: <em>"A landlord wants to pull a tenant's credit report."</em>
          </li>
          <li>
            <strong>Data → Citator</strong> — check <em>"Heintz v. Jenkins, 514 U.S. 291"</em>.
          </li>
          <li>
            <strong>Classifier</strong> — click <em>Train</em>, then classify a passage.
          </li>
        </ol>
      </div>

      {/* Feature sections */}
      <div className="space-y-2">
        {SECTIONS.map((s) => {
          const isOpen = open === s.id;
          return (
            <div key={s.id} className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <button
                onClick={() => setOpen(isOpen ? "" : s.id)}
                className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-50"
              >
                <span className="flex items-center gap-2">
                  <span className="text-lg">{s.icon}</span>
                  <span className="font-semibold text-slate-800">{s.title}</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
                    {s.tab} tab
                  </span>
                </span>
                <span className="text-slate-400">{isOpen ? "▾" : "▸"}</span>
              </button>
              {isOpen && (
                <div className="space-y-3 border-t border-slate-100 px-4 py-3 text-sm">
                  <p className="text-slate-700">{s.what}</p>
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">How to use</h4>
                    <ol className="mt-1 list-decimal space-y-1 pl-5 text-slate-700">
                      {s.steps.map((st, i) => (
                        <li key={i}>{st}</li>
                      ))}
                    </ol>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-indigo-500">
                      Real example — {s.example.label}
                    </div>
                    <p className="mt-1 text-slate-700">
                      <span className="font-medium">Try:</span> {s.example.input}
                    </p>
                    <p className="mt-1 text-slate-600">
                      <span className="font-medium">You'll get:</span> {s.example.result}
                    </p>
                  </div>
                  {s.note && <p className="text-xs text-slate-500">ℹ️ {s.note}</p>}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="rounded-lg border border-slate-300 bg-slate-50 p-3 text-center text-xs text-slate-600">
        General legal information, not legal advice — this is an educational tool and does not create
        an attorney-client relationship. Public/licensed legal data only · your uploaded documents
        stay on your machine · no web scraping, no PII gathering.
      </p>
    </div>
  );
}
