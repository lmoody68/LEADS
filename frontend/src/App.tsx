import { useState } from "react";
import ResearchView from "./views/ResearchView";
import MemoView from "./views/MemoView";
import ComplianceView from "./views/ComplianceView";
import DocumentView from "./views/DocumentView";
import TutorView from "./views/TutorView";

type Tab = "research" | "memo" | "compliance" | "document" | "tutor";

// One source of truth for the tab nav: label + a one-line "what this does" blurb
// shown under the header. Keeps the nav consistent and gives every tab a clear
// landing description (portfolio polish, Phase 6).
const TABS: { id: Tab; label: string; blurb: string }[] = [
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
];

export default function App() {
  const [tab, setTab] = useState<Tab>("research");
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-indigo-700">L.E.A.D.S.</h1>
              <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600">
                v1.0
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
          {tab === "research" ? (
            <ResearchView />
          ) : tab === "memo" ? (
            <MemoView />
          ) : tab === "compliance" ? (
            <ComplianceView />
          ) : tab === "document" ? (
            <DocumentView />
          ) : (
            <TutorView />
          )}
        </div>
        <p className="mt-4 text-center text-xs text-slate-400">
          Public/licensed legal data only · Uploaded documents stay local · General legal
          information, not legal advice.
        </p>
      </main>
    </div>
  );
}
