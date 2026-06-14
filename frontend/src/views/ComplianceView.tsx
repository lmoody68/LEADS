import { useState } from "react";
import {
  analyzeCompliance,
  type ComplianceResponse,
  type Citation,
} from "../lib/api";
import { ProviderBadge, Sources } from "../components/Sources";

const EXAMPLES = [
  "A debt collector wants to find a consumer's current employer and home address to collect on a default judgment. Is that permissible, and how should it be done?",
  "I want to find someone's home address from DMV records so I can show up and confront an ex.",
  "A landlord wants to pull a prospective tenant's consumer credit report before signing a lease. Is that allowed?",
];

const STAGES = [
  "Retrieving governing statutes (FDCPA/FCRA/DPPA/GLBA)…",
  "Reasoning through permissible purpose…",
  "Assembling restrictions, risks & compliant alternatives…",
];

function verdictStyle(verdict: string): { badge: string; label: string } {
  const v = (verdict || "").toLowerCase();
  if (v === "yes")
    return { badge: "bg-emerald-100 text-emerald-800 border-emerald-200", label: "Permissible purpose exists" };
  if (v === "no")
    return { badge: "bg-red-100 text-red-700 border-red-200", label: "Impermissible as framed" };
  return { badge: "bg-amber-100 text-amber-800 border-amber-200", label: "Depends on the conditions" };
}

// Map compliance citations to the shared Sources Citation shape (so the same
// source cards + credibility scoring affordance render here too).
function toCitations(c: ComplianceResponse["citations"]): Citation[] {
  return c.map((x) => ({
    source_title: x.source_title,
    citation: x.citation,
    url: x.url,
    snippet: x.snippet,
    doc_type: "statute",
    score: 0,
  }));
}

export default function ComplianceView() {
  const [scenario, setScenario] = useState("");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComplianceResponse | null>(null);

  async function run(s: string) {
    const text = s.trim();
    if (!text) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setStage(0);
    const timers = [
      window.setTimeout(() => setStage(1), 800),
      window.setTimeout(() => setStage(2), 2200),
    ];
    try {
      setResult(await analyzeCompliance(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      timers.forEach((t) => window.clearTimeout(t));
      setLoading(false);
    }
  }

  function onClear() {
    setScenario("");
    setResult(null);
    setError(null);
  }

  const verdict = result ? verdictStyle(result.permissible_purpose.verdict) : null;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Compliance &amp; Ethics Advisor</h2>
        <p className="text-sm text-slate-500">
          Describe an investigative scenario. The advisor retrieves the governing statutes
          (FDCPA, FCRA, DPPA, GLBA) and explains <strong>when the method is lawful vs. unlawful</strong>,
          flags the risks, and recommends <strong>compliant</strong> paths. It teaches boundaries —
          it never provides a how-to for unlawful skip tracing or PII gathering.
        </p>
      </div>

      <div className="space-y-2">
        <textarea
          className="w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          rows={3}
          placeholder="e.g. A debt collector wants to find a consumer's current employer and home address to collect on a default judgment. Is that permissible, and how should it be done?"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => run(scenario)}
            disabled={loading || !scenario.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
          <button
            onClick={onClear}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Clear
          </button>
        </div>

        {/* Example chips */}
        <div className="flex flex-wrap gap-2 pt-1">
          {EXAMPLES.map((ex, i) => (
            <button
              key={i}
              onClick={() => {
                setScenario(ex);
                void run(ex);
              }}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-left text-xs text-slate-600 hover:bg-slate-100"
              title={ex}
            >
              {ex.length > 70 ? ex.slice(0, 70) + "…" : ex}
            </button>
          ))}
        </div>
      </div>

      {/* Always-visible disclaimer */}
      <div className="rounded-lg border border-slate-300 bg-slate-50 p-3 text-xs text-slate-600">
        <strong className="text-slate-700">General legal information, not legal advice.</strong>{" "}
        This advisor is an educational tool. It does not create an attorney-client relationship.
        Consult a licensed attorney before acting.
      </div>

      {loading && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
          {STAGES[stage]}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !result && !error && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          A permissible-purpose verdict, governing statutes, restrictions, risk flags, and
          compliant alternatives will appear here.
        </p>
      )}

      {result && verdict && (
        <div className="space-y-4">
          {/* Verdict badge */}
          <div className={`rounded-lg border p-4 ${verdict.badge}`}>
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide opacity-70">
                  Permissible purpose
                </p>
                <p className="text-lg font-bold">{verdict.label}</p>
              </div>
              <ProviderBadge provider={result.provider} />
            </div>
            {result.permissible_purpose.explanation && (
              <p className="mt-2 text-sm leading-relaxed">
                {result.permissible_purpose.explanation}
              </p>
            )}
          </div>

          {/* Governing statutes */}
          {result.governing_statutes.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Governing statutes
              </h3>
              <ul className="space-y-2">
                {result.governing_statutes.map((g, i) => (
                  <li key={i} className="text-sm">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-medium text-slate-800">{g.name}</span>
                      {g.url ? (
                        <a
                          href={g.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-xs text-indigo-700 hover:underline"
                        >
                          {g.citation} →
                        </a>
                      ) : (
                        <span className="font-mono text-xs text-indigo-700">{g.citation}</span>
                      )}
                    </div>
                    {g.why && <p className="mt-0.5 text-slate-600">{g.why}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Restrictions */}
          {result.restrictions.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Restrictions
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                {result.restrictions.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Risk flags */}
          {result.risk_flags.length > 0 && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-red-700">
                ⚠ Risk flags
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-red-800">
                {result.risk_flags.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Compliant alternatives */}
          {result.compliant_alternatives.length > 0 && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                ✓ Compliant alternatives
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-emerald-800">
                {result.compliant_alternatives.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Citations (reuses the shared Sources component) */}
          {result.citations.length > 0 && <Sources citations={toCitations(result.citations)} />}

          {/* Prominent closing disclaimer */}
          <p className="rounded-lg border border-slate-300 bg-slate-100 p-3 text-center text-xs text-slate-600">
            {result.disclaimer}
          </p>
        </div>
      )}
    </div>
  );
}
