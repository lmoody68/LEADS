import { useState } from "react";
import { ask, type AnswerResponse } from "../lib/api";
import { ProviderBadge, Sources } from "../components/Sources";
import AnswerBody from "../components/AnswerBody";

const SAMPLE =
  "What did Heintz v. Jenkins hold about the FDCPA applying to attorneys?";

const STAGES = ["Planning the search…", "Searching case law…", "Retrieving…", "Synthesizing…"];

export default function ResearchView() {
  const [question, setQuestion] = useState("");
  const [deep, setDeep] = useState(true);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnswerResponse | null>(null);

  async function runAsk(q: string) {
    const query = q.trim();
    if (!query) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setStage(0);
    // Cosmetic progressive status while the request is in flight.
    const timers = [
      window.setTimeout(() => setStage(1), 500),
      window.setTimeout(() => setStage(2), 1400),
      window.setTimeout(() => setStage(3), 2600),
    ];
    try {
      setResult(await ask(query, deep));
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
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Deep-Research Engine</h2>
        <p className="text-sm text-slate-500">
          Ask a legal question. With <strong>Deep research</strong> on, L.E.A.D.S. plans the
          search, pulls live court opinions from CourtListener, and grounds a cited answer in
          both the statutory corpus (FDCPA, FCRA, DPPA, GLBA) and real case law.
        </p>
      </div>

      <div className="space-y-2">
        <textarea
          className="w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          rows={3}
          placeholder="e.g. What did Heintz v. Jenkins hold about the FDCPA applying to attorneys?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => runAsk(question)}
            disabled={loading || !question.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Researching…" : "Research"}
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
            <span title="On: query live case law via CourtListener. Off: seeded statutes only.">
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
        <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
          {deep ? STAGES[stage] : "Searching seeded statutes…"}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !result && !error && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          Your cited answer, sources, and the AI's reasoning will appear here.
        </p>
      )}

      {result && (
        <div className="space-y-4">
          {/* AI transparency panel */}
          {(result.rewritten_query || (result.legal_issues && result.legal_issues.length > 0)) && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                AI reasoning
              </h3>
              {result.rewritten_query && (
                <p className="text-slate-700">
                  <span className="font-medium text-slate-500">Rewritten search query: </span>
                  <span className="font-mono text-indigo-700">{result.rewritten_query}</span>
                </p>
              )}
              {result.legal_issues && result.legal_issues.length > 0 && (
                <div className="mt-1">
                  <span className="font-medium text-slate-500">Identified legal issues:</span>
                  <ul className="mt-0.5 list-disc pl-5 text-slate-700">
                    {result.legal_issues.map((iss, i) => (
                      <li key={i}>{iss}</li>
                    ))}
                  </ul>
                </div>
              )}
              {result.ingested && result.ingested.length > 0 && (
                <p className="mt-1 text-xs text-slate-500">
                  Pulled {result.ingested.length} live opinion(s) from CourtListener:{" "}
                  {result.ingested.map((c) => c.case_name).join("; ")}
                </p>
              )}
              {result.retrieval && (
                <p className="mt-1 text-xs text-slate-400">
                  Hybrid retrieval — dense top:{" "}
                  {(result.retrieval.dense_top || []).map((d) => d.citation).slice(0, 3).join(", ") || "—"}{" "}
                  · BM25 top:{" "}
                  {(result.retrieval.bm25_top || []).map((d) => d.citation).slice(0, 3).join(", ") || "—"}{" "}
                  · fused {result.retrieval.fused ?? 0} candidates (RRF)
                </p>
              )}
            </div>
          )}

          {/* Answer */}
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Answer
              </h3>
              <ProviderBadge provider={result.provider} />
            </div>
            <AnswerBody text={result.answer} />

            {result.grounding && (
              <p className="mt-3 flex items-start gap-2 rounded border border-emerald-100 bg-emerald-50 p-2 text-xs text-emerald-800">
                <span className="font-semibold">Grounding:</span>
                <span>{result.grounding}</span>
              </p>
            )}
          </div>

          {/* Conflicts / agreement callouts */}
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

          {/* Follow-up chips */}
          {result.followups && result.followups.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Follow-up questions
              </h3>
              <div className="flex flex-wrap gap-2">
                {result.followups.map((f, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setQuestion(f);
                      void runAsk(f);
                    }}
                    className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-100"
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
          )}

          <Sources citations={result.citations} />
        </div>
      )}
    </div>
  );
}
