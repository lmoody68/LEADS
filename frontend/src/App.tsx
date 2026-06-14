import { useState } from "react";
import ResearchView from "./views/ResearchView";
import MemoView from "./views/MemoView";
import ComplianceView from "./views/ComplianceView";
import DocumentView from "./views/DocumentView";

type Tab = "research" | "memo" | "compliance" | "document";

export default function App() {
  const [tab, setTab] = useState<Tab>("research");

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-indigo-700">L.E.A.D.S.</h1>
            <p className="text-xs text-slate-500">Legal Education &amp; Analytical Deep-Search</p>
          </div>
          <nav className="flex gap-1 rounded-lg bg-slate-100 p-1">
            <button
              onClick={() => setTab("research")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                tab === "research"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-800"
              }`}
            >
              Research
            </button>
            <button
              onClick={() => setTab("memo")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                tab === "memo"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-800"
              }`}
            >
              Research Memo
            </button>
            <button
              onClick={() => setTab("compliance")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                tab === "compliance"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-800"
              }`}
            >
              Compliance Advisor
            </button>
            <button
              onClick={() => setTab("document")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                tab === "document"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-800"
              }`}
            >
              Document Analysis
            </button>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          {tab === "research" ? (
            <ResearchView />
          ) : tab === "memo" ? (
            <MemoView />
          ) : tab === "compliance" ? (
            <ComplianceView />
          ) : (
            <DocumentView />
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
