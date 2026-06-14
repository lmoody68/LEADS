import { useState } from "react";
import { ask, type AnswerResponse } from "../lib/api";
import { ProviderBadge, Sources } from "../components/Sources";

const SAMPLE =
  "Under the FDCPA, when may a debt collector contact third parties about a consumer's location?";

export default function ResearchView() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnswerResponse | null>(null);

  async function onAsk() {
    const q = question.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await ask(q));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
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
          Ask a question over the public legal corpus (FDCPA, FCRA, DPPA, GLBA). Answers are
          grounded in and cited to the statutory text.
        </p>
      </div>

      <div className="space-y-2">
        <textarea
          className="w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          rows={3}
          placeholder="e.g. Under the FDCPA, when may a debt collector contact third parties about a consumer's location?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={onAsk}
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
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !result && !error && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          Your cited answer will appear here.
        </p>
      )}

      {result && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Answer
              </h3>
              <ProviderBadge provider={result.provider} />
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
              {result.answer}
            </p>
          </div>
          <Sources citations={result.citations} />
        </div>
      )}
    </div>
  );
}
