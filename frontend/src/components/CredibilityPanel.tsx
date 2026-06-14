import { useState } from "react";
import {
  scoreCredibility,
  type CredibilityInput,
  type CredibilityResponse,
} from "../lib/api";

function barColor(score: number): string {
  if (score >= 75) return "bg-emerald-500";
  if (score >= 50) return "bg-amber-500";
  return "bg-red-500";
}

function totalColor(score: number): string {
  if (score >= 75) return "text-emerald-700";
  if (score >= 50) return "text-amber-700";
  return "text-red-700";
}

/**
 * Lightweight, reusable credibility dashboard. Renders a "Score credibility"
 * toggle; on first open it calls /api/credibility with the supplied input
 * (source_id from a prior result, or pasted title/citation/text), then shows the
 * 5 weighted dimension bars + weighted total + tier badge + flags + corroboration.
 */
export default function CredibilityPanel({ input }: { input: CredibilityInput }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CredibilityResponse | null>(null);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !result && !loading) {
      setLoading(true);
      setError(null);
      try {
        const r = await scoreCredibility(input);
        if (r.error) setError(r.error);
        else setResult(r);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <div className="mt-2">
      <button
        onClick={toggle}
        className="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
        aria-expanded={open}
      >
        <span>📊 Score credibility</span>
        <span className="text-[10px] text-indigo-400">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
          {loading && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
              Scoring across 5 weighted dimensions…
            </div>
          )}

          {error && (
            <p className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">
              {error}
            </p>
          )}

          {result && (
            <div className="space-y-3">
              {/* Header: weighted total + tier */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="text-xs uppercase tracking-wide text-slate-500">
                    Weighted credibility
                  </span>
                  <div className={`text-2xl font-bold ${totalColor(result.weighted_total)}`}>
                    {result.weighted_total.toFixed(1)}
                    <span className="text-sm font-normal text-slate-400"> / 100</span>
                  </div>
                </div>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
                    result.tier === "primary"
                      ? "bg-violet-100 text-violet-700"
                      : "bg-slate-200 text-slate-600"
                  }`}
                  title="Primary = court/legislature/regulator; Secondary = commentary/news/derivative."
                >
                  {result.tier} authority
                </span>
              </div>

              {/* Dimension bars */}
              <div className="space-y-2">
                {result.dimensions.map((d) => (
                  <div key={d.name}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-700">
                        {d.name}
                        <span className="ml-1 text-slate-400">
                          ({Math.round(d.weight * 100)}%)
                        </span>
                      </span>
                      <span className="font-mono text-slate-500">{d.score_0_100}/100</span>
                    </div>
                    <div className="mt-0.5 h-2 w-full overflow-hidden rounded-full bg-slate-200">
                      <div
                        className={`h-full rounded-full ${barColor(d.score_0_100)}`}
                        style={{ width: `${Math.max(0, Math.min(100, d.score_0_100))}%` }}
                      />
                    </div>
                    {d.rationale && d.rationale !== "—" && (
                      <p className="mt-0.5 text-[11px] leading-snug text-slate-500">
                        {d.rationale}
                      </p>
                    )}
                  </div>
                ))}
              </div>

              {/* Corroboration */}
              {(result.corroboration.agreeing.length > 0 ||
                result.corroboration.conflicting.length > 0) && (
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-emerald-100 bg-emerald-50 p-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                      Agreeing sources
                    </p>
                    {result.corroboration.agreeing.length > 0 ? (
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-emerald-800">
                        {result.corroboration.agreeing.map((a, i) => (
                          <li key={i}>{a}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-[11px] text-emerald-700/70">None noted.</p>
                    )}
                  </div>
                  <div className="rounded border border-amber-100 bg-amber-50 p-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
                      Conflicting sources
                    </p>
                    {result.corroboration.conflicting.length > 0 ? (
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-amber-800">
                        {result.corroboration.conflicting.map((c, i) => (
                          <li key={i}>{c}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-[11px] text-amber-700/70">None noted.</p>
                    )}
                  </div>
                </div>
              )}

              {/* Flags */}
              {result.flags.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    Flags
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-slate-600">
                    {result.flags.map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Shepardize heuristic (clearly labeled, not authoritative) */}
              {result.shepardize_heuristic && (
                <p className="rounded border border-slate-200 bg-white p-2 text-[11px] leading-snug text-slate-500">
                  {result.shepardize_heuristic}
                </p>
              )}

              <p className="text-right text-[10px] text-slate-400">
                scored by {result.provider}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
