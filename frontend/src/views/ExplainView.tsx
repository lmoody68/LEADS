import { useState } from "react";
import {
  explainPlain,
  caseBrief,
  type ExplainResult,
  type CaseBriefResult,
} from "../lib/api";

type Mode = "plain" | "brief";

export default function ExplainView() {
  const [mode, setMode] = useState<Mode>("plain");
  const [text, setText] = useState("");
  const [citation, setCitation] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [plain, setPlain] = useState<ExplainResult | null>(null);
  const [brief, setBrief] = useState<CaseBriefResult | null>(null);

  const canRun = text.trim().length > 0 || citation.trim().length > 0;

  async function run() {
    if (!canRun) return;
    setLoading(true);
    setErr(null);
    setPlain(null);
    setBrief(null);
    const input = { text: text.trim() || undefined, citation: citation.trim() || undefined };
    try {
      if (mode === "plain") setPlain(await explainPlain(input));
      else setBrief(await caseBrief(input));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function clearAll() {
    setText("");
    setCitation("");
    setPlain(null);
    setBrief(null);
    setErr(null);
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Explain</h2>
        <p className="text-sm text-slate-500">
          Paste legal text/jargon or enter a case citation, then either{" "}
          <strong>transcribe it into plain English</strong> for a juror or non-lawyer, or generate a{" "}
          <strong>structured IRAC case brief</strong>.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setMode("plain")}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            mode === "plain" ? "bg-indigo-600 text-white" : "border border-slate-300 text-slate-600 hover:bg-slate-50"
          }`}
        >
          🗣️ Plain English (for jurors)
        </button>
        <button
          onClick={() => setMode("brief")}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            mode === "brief" ? "bg-indigo-600 text-white" : "border border-slate-300 text-slate-600 hover:bg-slate-50"
          }`}
        >
          📋 Case Brief (IRAC)
        </button>
      </div>

      {/* Inputs */}
      <textarea
        className="h-36 w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder="Paste the legal text, opinion excerpt, or jargon to explain…"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="min-w-[260px] flex-1 rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder='…or a citation to pull the case — e.g. "Heintz v. Jenkins, 514 U.S. 291"'
          value={citation}
          onChange={(e) => setCitation(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void run()}
        />
        <button
          onClick={() => void run()}
          disabled={loading || !canRun}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Working…" : mode === "plain" ? "Transcribe" : "Brief it"}
        </button>
        <button
          onClick={clearAll}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
        >
          Clear
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
          {mode === "plain" ? "Transcribing into plain English…" : "Building the IRAC brief…"}
          {citation.trim() && " (fetching the case may take a few seconds)"}
        </div>
      )}

      {err && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{err}</div>}

      {/* Empty state */}
      {!loading && !err && !plain && !brief && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          {mode === "plain"
            ? "The layman's-terms transcriber rewrites legal jargon into plain English, with a glossary, an everyday analogy, and a bottom line."
            : "The case-brief tool extracts Issue · Rule · Analysis · Holding from an opinion."}
        </p>
      )}

      {/* Plain-English result */}
      {plain && (
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          {plain.note && (
            <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">{plain.note}</div>
          )}
          {plain.overview && <p className="font-medium text-slate-800">{plain.overview}</p>}
          {plain.plain_transcription && (
            <Section title="In plain English">
              <p className="whitespace-pre-wrap text-slate-700">{plain.plain_transcription}</p>
            </Section>
          )}
          {plain.step_by_step.length > 0 && (
            <Section title="Step by step">
              <ul className="list-disc space-y-1 pl-5 text-slate-700">
                {plain.step_by_step.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </Section>
          )}
          {plain.glossary.length > 0 && (
            <Section title="Glossary (the jargon, decoded)">
              <dl className="space-y-1">
                {plain.glossary.map((g, i) => (
                  <div key={i} className="flex flex-wrap gap-1">
                    <dt className="font-semibold text-slate-800">{g.term}:</dt>
                    <dd className="text-slate-600">{g.meaning}</dd>
                  </div>
                ))}
              </dl>
            </Section>
          )}
          {plain.analogy && (
            <Section title="Think of it like…">
              <p className="text-slate-700">{plain.analogy}</p>
            </Section>
          )}
          {plain.why_it_matters && (
            <Section title="Why it matters">
              <p className="text-slate-700">{plain.why_it_matters}</p>
            </Section>
          )}
          {plain.bottom_line && (
            <div className="rounded-lg bg-indigo-50 p-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-indigo-500">Bottom line</span>
              <p className="text-slate-800">{plain.bottom_line}</p>
            </div>
          )}
          <Footer provider={plain.provider} url={plain.url} disclaimer={plain.disclaimer} excerpt={plain.source_excerpt} />
        </div>
      )}

      {/* IRAC brief result */}
      {brief && (
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          {brief.note && (
            <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">{brief.note}</div>
          )}
          <div className="flex flex-wrap items-baseline gap-2">
            <h3 className="text-base font-semibold text-slate-800">{brief.case_name || "Case brief"}</h3>
            {brief.citation && <span className="text-xs text-slate-500">{brief.citation}</span>}
            {brief.disposition && (
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{brief.disposition}</span>
            )}
          </div>
          {brief.synopsis && <p className="italic text-slate-600">{brief.synopsis}</p>}
          {brief.facts && <Section title="Facts"><p className="text-slate-700">{brief.facts}</p></Section>}
          {brief.procedural_history && (
            <Section title="Procedural history"><p className="text-slate-700">{brief.procedural_history}</p></Section>
          )}
          {brief.issues.length > 0 && (
            <Section title="Issue(s)">
              <ul className="list-disc space-y-1 pl-5 text-slate-700">
                {brief.issues.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </Section>
          )}
          {brief.rule && <Section title="Rule"><p className="text-slate-700">{brief.rule}</p></Section>}
          {brief.analysis && <Section title="Analysis / Application"><p className="text-slate-700">{brief.analysis}</p></Section>}
          {brief.holding && (
            <div className="rounded-lg bg-indigo-50 p-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-indigo-500">Holding</span>
              <p className="text-slate-800">{brief.holding}</p>
            </div>
          )}
          {brief.key_quotes.length > 0 && (
            <Section title="Key quotes">
              <ul className="space-y-1 pl-1 text-slate-600">
                {brief.key_quotes.map((q, i) => (
                  <li key={i} className="border-l-2 border-slate-300 pl-2 italic">“{q}”</li>
                ))}
              </ul>
            </Section>
          )}
          <Footer provider={brief.provider} url={brief.url} disclaimer={brief.disclaimer} excerpt={brief.source_excerpt} />
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h4>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function Footer({
  provider,
  url,
  disclaimer,
  excerpt,
}: {
  provider: string;
  url?: string;
  disclaimer: string;
  excerpt?: string;
}) {
  return (
    <div className="space-y-1 border-t border-slate-100 pt-2">
      {excerpt && (
        <details className="text-xs text-slate-500">
          <summary className="cursor-pointer hover:text-slate-700">Source excerpt</summary>
          <p className="mt-1 whitespace-pre-wrap text-slate-500">{excerpt}</p>
        </details>
      )}
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
        <span>provider: {provider}</span>
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline">
            view source
          </a>
        )}
      </div>
      <p className="text-[11px] text-slate-400">{disclaimer}</p>
    </div>
  );
}
