import { useState, useEffect } from "react";
import ResearchView from "./views/ResearchView";
import MemoView from "./views/MemoView";
import ComplianceView from "./views/ComplianceView";
import DocumentView from "./views/DocumentView";
import TutorView from "./views/TutorView";
import DataView from "./views/DataView";
import ExplainView from "./views/ExplainView";
import ClassifierView from "./views/ClassifierView";
import GuideView from "./views/GuideView";
import StudyView from "./views/StudyView";
import AssistantView from "./views/AssistantView";

type Tab =
  | "guide"
  | "assistant"
  | "research"
  | "memo"
  | "explain"
  | "study"
  | "compliance"
  | "document"
  | "tutor"
  | "data"
  | "classifier";

// One source of truth for the tab nav: label + a one-line "what this does" blurb
// shown under the header. Keeps the nav consistent and gives every tab a clear
// landing description (portfolio polish, Phase 6).
const TABS: { id: Tab; label: string; blurb: string }[] = [
  {
    id: "guide",
    label: "Guide",
    blurb:
      "How to use L.E.A.D.S. — what each feature does, step-by-step, with real-world examples you can copy.",
  },
  {
    id: "assistant",
    label: "Assistant",
    blurb:
      "Ask anything in plain language — an agentic orchestrator routes your request to the right tool (research, case brief, plain-English, compliance, citator, related authorities, flashcards, outline, classify) and answers.",
  },
  {
    id: "research",
    label: "Research",
    blurb:
      "Deep-search RAG over public statutes + live CourtListener case law — hybrid (dense + BM25 + RRF) retrieval with grounded, cited answers and conflict detection.",
  },
  {
    id: "memo",
    label: "Research Memo",
    blurb:
      "Agentic multi-step memo: Planner → Retriever → Synthesizer → Drafter → Citer → Reviewer produces a structured legal memo with inline citations to real sources.",
  },
  {
    id: "explain",
    label: "Explain",
    blurb:
      "Layman's-terms transcriber: paste legal jargon or a citation and get it rewritten in plain English for a juror (glossary, analogy, bottom line) — or a structured IRAC case brief.",
  },
  {
    id: "study",
    label: "Study Mode",
    blurb:
      "A general-purpose learning toolkit: flashcards, issue-spotter hypos with grading, a Bluebook citation formatter, related-authorities search, and study outlines — built on free public legal data.",
  },
  {
    id: "compliance",
    label: "Compliance Advisor",
    blurb:
      "Teaching/advisory only: describe a scenario and get a statute-grounded analysis (FCRA/FDCPA/DPPA/GLBA) — permissible purpose, restrictions, risks, and lawful alternatives.",
  },
  {
    id: "document",
    label: "Document Analysis",
    blurb:
      "Upload documents you lawfully possess: entity + relationship mapping, timeline, cross-document patterns, and PII redaction suggestions. Files stay local.",
  },
  {
    id: "tutor",
    label: "Tutor",
    blurb:
      "Adaptive investigative-methodology tutor powered by Bayesian Knowledge Tracing (BKT) — lessons, quizzes, a practice sandbox, and a red/yellow/green mastery dashboard.",
  },
  {
    id: "classifier",
    label: "Classifier",
    blurb:
      "Supervised-ML showcase: MiniLM corpus embeddings → a logistic-regression head that tags a document's type (statute/opinion/regulation/bill), with honest held-out + cross-validated metrics and a live try-it box.",
  },
  {
    id: "data",
    label: "Data",
    blurb:
      "Admin/ingestion: grow the corpus from official public-data APIs (CourtListener, govinfo) and discover public legal datasets (Hugging Face Hub). Official APIs only — no scraping, no PII.",
  },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("guide");
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];

  // Keep-alive: mount each tab on first visit and keep it mounted (just hidden when
  // inactive) so in-progress searches, typed queries, and results survive tab switches.
  const [mounted, setMounted] = useState<Set<Tab>>(() => new Set<Tab>(["guide"]));
  useEffect(() => {
    setMounted((prev) => (prev.has(tab) ? prev : new Set(prev).add(tab)));
  }, [tab]);

  const renderView = (id: Tab) => {
    switch (id) {
      case "guide": return <GuideView />;
      case "assistant": return <AssistantView />;
      case "research": return <ResearchView />;
      case "memo": return <MemoView />;
      case "explain": return <ExplainView />;
      case "study": return <StudyView />;
      case "compliance": return <ComplianceView />;
      case "document": return <DocumentView />;
      case "tutor": return <TutorView />;
      case "classifier": return <ClassifierView />;
      case "data": return <DataView />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-indigo-700">L.E.A.D.S.</h1>
              <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600">
                v1.2
              </span>
            </div>
            <p className="text-xs text-slate-500">Legal Education &amp; Analytical Deep-Search</p>
          </div>
          <nav className="flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                aria-current={tab === t.id ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  tab === t.id
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-slate-600 hover:text-slate-800"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-6">
        {/* Per-tab landing blurb so each feature is self-describing. */}
        <p className="mb-3 text-sm text-slate-500">{active.blurb}</p>
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          {/* Keep-alive: render every visited tab, hide the inactive ones with CSS so
              their state (queries, results, running searches) is never lost. */}
          {TABS.filter((t) => mounted.has(t.id)).map((t) => (
            <div key={t.id} style={{ display: tab === t.id ? undefined : "none" }}>
              {renderView(t.id)}
            </div>
          ))}
        </div>
        <p className="mt-4 text-center text-xs text-slate-400">
          Public/licensed legal data only · Uploaded documents stay local · General legal
          information, not legal advice.
        </p>
      </main>
    </div>
  );
}
