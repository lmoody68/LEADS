import type { Citation } from "../lib/api";

export function ProviderBadge({ provider }: { provider: string }) {
  const isExtractive = provider.startsWith("extractive");
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
        isExtractive
          ? "bg-amber-100 text-amber-800"
          : "bg-emerald-100 text-emerald-800"
      }`}
      title={
        isExtractive
          ? "No LLM key configured — answer is the top retrieved passages with citations."
          : `Synthesized by ${provider}`
      }
    >
      {isExtractive ? "extractive (no LLM key)" : `answered by ${provider}`}
    </span>
  );
}

export function Sources({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="text-sm text-slate-500">No sources.</p>;
  }
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Sources
      </h3>
      {citations.map((c, i) => (
        <div
          key={i}
          className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-medium text-slate-800">{c.source_title}</p>
              <p className="font-mono text-xs text-indigo-700">{c.citation}</p>
            </div>
            <span className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
              score {c.score.toFixed(3)}
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">{c.snippet}</p>
        </div>
      ))}
    </div>
  );
}
