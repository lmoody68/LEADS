import { useState } from "react";
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

function SourceCard({ c, index }: { c: Citation; index: number }) {
  const [open, setOpen] = useState(false);
  const isOpinion = c.doc_type === "opinion";
  const long = c.snippet.length > 320;
  const preview = open || !long ? c.snippet : c.snippet.slice(0, 320) + "…";

  return (
    <div
      id={`source-${index}`}
      className="scroll-mt-24 rounded-lg border border-slate-200 bg-white p-3 shadow-sm transition target:ring-2 target:ring-indigo-400"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">
              {index}
            </span>
            <p className="truncate font-medium text-slate-800">{c.source_title}</p>
          </div>
          <p className="mt-0.5 font-mono text-xs text-indigo-700">{c.citation}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                isOpinion
                  ? "bg-violet-100 text-violet-700"
                  : "bg-sky-100 text-sky-700"
              }`}
            >
              {isOpinion ? "case law" : "statute"}
            </span>
            {isOpinion && c.legal_section && c.legal_section !== "opinion" && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-600">
                {c.legal_section}
              </span>
            )}
            {c.court && (
              <span className="text-[11px] text-slate-500">
                {c.court}
                {c.date ? ` · ${c.date}` : ""}
              </span>
            )}
          </div>
        </div>
        <span className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          score {c.score.toFixed(3)}
        </span>
      </div>

      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
        {preview}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        {long && (
          <button
            onClick={() => setOpen((v) => !v)}
            className="text-xs font-medium text-indigo-600 hover:underline"
          >
            {open ? "Show less" : "Show more"}
          </button>
        )}
        {c.url && (
          <a
            href={c.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-medium text-violet-600 hover:underline"
          >
            View on CourtListener →
          </a>
        )}
      </div>
    </div>
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
        <SourceCard key={i} c={c} index={i + 1} />
      ))}
    </div>
  );
}
