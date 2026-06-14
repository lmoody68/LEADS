import { useState } from "react";
import {
  generateMemo,
  type MemoResponse,
  type MemoSource,
  type Citation,
} from "../lib/api";
import { ProviderBadge, Sources } from "../components/Sources";
import AnswerBody from "../components/AnswerBody";

const SAMPLE =
  "Are debt-collection attorneys liable under the FDCPA, and what are the key limits or exceptions?";

// Staged progress mirrors the backend agent pipeline so the user can SEE the
// multi-step reasoning while the (20-60s) request is in flight.
const STAGES = [
  "Planning — decomposing into sub-questions…",
  "Researching each sub-question (live case law)…",
  "Synthesizing across findings…",
  "Drafting the memo…",
  "Reviewing & citing…",
];

function confColor(c: string): string {
  if (c === "high") return "bg-emerald-100 text-emerald-800";
  if (c === "low") return "bg-red-100 text-red-700";
  return "bg-amber-100 text-amber-800"; // medium / unknown
}

// Map a MemoSource[] to the Citation[] shape the shared Sources component renders
// (so the inline [n] chips from AnswerBody scroll to the same #source-N cards).
function toCitations(sources: MemoSource[]): Citation[] {
  return sources.map((s) => ({
    source_title: s.source_title,
    citation: s.citation,
    section: s.legal_section,
    court: s.court,
    date: s.date,
    url: s.url,
    doc_type: s.doc_type,
    legal_section: s.legal_section,
    snippet: s.snippet,
    score: s.score ?? 0,
  }));
}

export default function MemoView() {
  const [question, setQuestion] = useState("");
  const [deep, setDeep] = useState(true);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MemoResponse | null>(null);
  const [copied, setCopied] = useState(false);

  async function run(q: string) {
    const query = q.trim();
    if (!query) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setStage(0);
    // Cosmetic staged progress while the agent runs server-side.
    const timers = [
      window.setTimeout(() => setStage(1), 1500),
      window.setTimeout(() => setStage(2), 8000),
      window.setTimeout(() => setStage(3), 13000),
      window.setTimeout(() => setStage(4), 18000),
    ];
    try {
      setResult(await generateMemo(query, deep));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      timers.forEach((t) => window.clearTimeout(t));
      setLoading(false);
    }
  }

  function onClear() {
    setQuestion("");
    setResult(null);
    setError(null);
    setCopied(false);
  }

  function exportMarkdown() {
    if (!result) return;
    const blob = new Blob([result.memo_markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "leads-research-memo.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copyMarkdown() {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.memo_markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard may be blocked; export button is the fallback */
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Agentic Research Memo</h2>
        <p className="text-sm text-slate-500">
          A multi-step AI agent <strong>plans</strong> your question into sub-questions,{" "}
          <strong>researches</strong> each against live case law + statutes,{" "}
          <strong>synthesizes</strong>, <strong>drafts</strong> a structured memo with inline
          citations, then <strong>self-reviews</strong> it for unsupported claims.
        </p>
      </div>

      <div className="space-y-2">
        <textarea
          className="w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          rows={3}
          placeholder="Ask a complex legal research question, e.g. Are debt-collection attorneys liable under the FDCPA, and what are the key limits or exceptions?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => run(question)}
            disabled={loading || !question.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Generating memo…" : "Generate Memo"}
          </button>
          <button
            onClick={() => setQuestion(SAMPLE)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Use sample question
          </button>
          <button
            onClick={onClear}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Clear
          </button>

          <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm text-slate-600">
            <span title="On: research each sub-question against live CourtListener case law. Off: seeded statutes only.">
              Deep research (live case law)
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={deep}
              onClick={() => setDeep((v) => !v)}
              className={`relative h-6 w-11 rounded-full transition ${
                deep ? "bg-indigo-600" : "bg-slate-300"
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
                  deep ? "left-[22px]" : "left-0.5"
                }`}
              />
            </button>
          </label>
        </div>
      </div>

      {loading && (
        <div className="space-y-2 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
            <span className="font-medium">{STAGES[stage]}</span>
          </div>
          <ol className="ml-6 space-y-0.5 text-xs">
            {STAGES.map((s, i) => (
              <li
                key={i}
                className={
                  i < stage
                    ? "text-indigo-400 line-through"
                    : i === stage
                    ? "font-semibold text-indigo-700"
                    : "text-indigo-300"
                }
              >
                {i + 1}. {s.replace(/…$/, "")}
              </li>
            ))}
          </ol>
          <p className="ml-6 text-xs text-indigo-400">
            The agent makes several LLM + retrieval calls — this can take 20–60s.
          </p>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !result && !error && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          Your structured research memo — sub-question plan, cited analysis, conflicts, and the
          AI's self-review — will appear here.
        </p>
      )}

      {result && (
        <div className="space-y-4">
          {/* Sub-question plan (AI transparency) */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
            <div className="mb-1.5 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Research plan (sub-questions)
              </h3>
              <ProviderBadge provider={result.provider} />
            </div>
            <ol className="list-decimal space-y-1 pl-5 text-slate-700">
              {result.plan.map((sq, i) => (
                <li key={i}>
                  {sq}
                  {result.subq_sources[sq] && result.subq_sources[sq].length > 0 && (
                    <span className="ml-1 text-xs text-slate-400">
                      → sources {result.subq_sources[sq].join(", ")}
                    </span>
                  )}
                </li>
              ))}
            </ol>
            {result.ingested && result.ingested.length > 0 && (
              <p className="mt-2 text-xs text-slate-500">
                Pulled {result.ingested.length} live opinion(s) from CourtListener:{" "}
                {result.ingested.map((c) => c.case_name).filter(Boolean).join("; ")}
              </p>
            )}
            <p className="mt-1 text-xs text-slate-400">
              Pipeline:{" "}
              {["planner", "synthesizer", "drafter", "reviewer"]
                .map((k) => `${k}=${result.providers[k] ?? "—"}`)
                .join(" · ")}
            </p>
          </div>

          {/* Export / copy controls */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={copyMarkdown}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              {copied ? "Copied ✓" : "Copy memo (markdown)"}
            </button>
            <button
              onClick={exportMarkdown}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              Export .md
            </button>
            {result.grounding && (
              <span className="ml-auto text-xs text-slate-400">{result.grounding}</span>
            )}
          </div>

          {/* The memo — one card per section with a confidence badge */}
          <div className="space-y-3">
            {result.sections.map((sec, i) => (
              <div key={i} className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-slate-800">{sec.title}</h3>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${confColor(
                      sec.confidence
                    )}`}
                    title="Reviewer's confidence that this section is grounded in cited sources."
                  >
                    {sec.confidence} confidence
                  </span>
                </div>
                <AnswerBody text={sec.body} />
              </div>
            ))}
          </div>

          {/* Conflicts */}
          {result.conflicts && result.conflicts.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-700">
                ⚠ Conflicts / qualifications between sources
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">
                {result.conflicts.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Gaps */}
          {result.gaps && result.gaps.length > 0 && (
            <div className="rounded-lg border border-sky-200 bg-sky-50 p-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-sky-700">
                Gaps the retrieved sources do not cover
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-sky-800">
                {result.gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Reviewer self-check */}
          {result.reviewer_notes && result.reviewer_notes.length > 0 && (
            <div className="rounded-lg border border-violet-200 bg-violet-50 p-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-violet-700">
                Reviewer self-check
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-violet-800">
                {result.reviewer_notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Citer notes (only if it had to scrub bad markers) */}
          {result.citer_notes && result.citer_notes.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Citation verification
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
                {result.citer_notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Ordered sources — inline [n] chips above scroll to these */}
          <Sources citations={toCitations(result.sources)} />
        </div>
      )}
    </div>
  );
}
