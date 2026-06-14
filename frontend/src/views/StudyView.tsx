import { useState } from "react";
import {
  studyFlashcards,
  studyHypo,
  studyHypoEvaluate,
  studyCite,
  studySimilar,
  studyOutline,
  type FlashcardsResult,
  type HypoResult,
  type HypoEvalResult,
  type CiteResult,
  type SimilarResult,
  type OutlineResult,
} from "../lib/api";

type Mode = "flashcards" | "hypo" | "cite" | "research";

const MODES: { id: Mode; label: string }[] = [
  { id: "flashcards", label: "🃏 Flashcards" },
  { id: "hypo", label: "🧩 Issue-Spotter" },
  { id: "cite", label: "📑 Bluebook Cite" },
  { id: "research", label: "🔗 Related & Outline" },
];

function useErr() {
  const [err, setErr] = useState<string | null>(null);
  return { err, setErr };
}

export default function StudyView() {
  const [mode, setMode] = useState<Mode>("flashcards");
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Study Mode</h2>
        <p className="text-sm text-slate-500">
          A general-purpose learning &amp; practice toolkit built on free public legal data — make
          flashcards, drill issue-spotting, format Bluebook citations, find related authorities, and
          build outlines. General legal information, not legal advice.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              mode === m.id ? "bg-indigo-600 text-white" : "border border-slate-300 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "flashcards" && <Flashcards />}
      {mode === "hypo" && <IssueSpotter />}
      {mode === "cite" && <CiteFormatter />}
      {mode === "research" && <ResearchAids />}
    </div>
  );
}

function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
      {label}
    </div>
  );
}
function ErrBox({ msg }: { msg: string }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{msg}</div>;
}
function InfoBox({ msg }: { msg: string }) {
  return <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">{msg}</div>;
}

// ---------------- Flashcards ----------------
function Flashcards() {
  const [topic, setTopic] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const { err, setErr } = useErr();
  const [res, setRes] = useState<FlashcardsResult | null>(null);
  const [flipped, setFlipped] = useState<Record<number, boolean>>({});

  async function go() {
    if (!topic.trim() && !text.trim()) return;
    setLoading(true);
    setErr(null);
    setRes(null);
    setFlipped({});
    try {
      setRes(await studyFlashcards({ topic: topic.trim() || undefined, text: text.trim() || undefined }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <input
        className="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder="Topic — e.g. FDCPA debt-collector restrictions"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
      />
      <textarea
        className="h-20 w-full resize-y rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder="…or paste text (a case, a statute section) to make cards from"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex gap-2">
        <button onClick={() => void go()} disabled={loading || (!topic.trim() && !text.trim())}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {loading ? "Making cards…" : "Make flashcards"}
        </button>
        <button onClick={() => { setTopic(""); setText(""); setRes(null); setErr(null); }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50">Clear</button>
      </div>
      {loading && <Spinner label="Generating flashcards…" />}
      {err && <ErrBox msg={err} />}
      {res && res.note && <div className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">{res.note}</div>}
      {res && res.cards.length === 0 && (
        <p className="rounded-lg border border-dashed border-slate-300 p-5 text-center text-sm text-slate-400">
          No cards generated. Try a broader topic, or paste more text.
        </p>
      )}
      {res && res.cards.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {res.cards.map((c, i) => (
            <button key={i} onClick={() => setFlipped((f) => ({ ...f, [i]: !f[i] }))}
              className="min-h-[88px] rounded-lg border border-slate-200 bg-white p-3 text-left text-sm hover:border-indigo-300">
              <div className="text-[10px] uppercase tracking-wide text-slate-400">{flipped[i] ? "answer" : "term — tap to flip"}</div>
              <div className="mt-1 text-slate-800">{flipped[i] ? c.back : c.front}</div>
            </button>
          ))}
        </div>
      )}
      {res && <p className="text-[11px] text-slate-400">{res.disclaimer}</p>}
    </div>
  );
}

// ---------------- Issue-Spotter ----------------
function IssueSpotter() {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const { err, setErr } = useErr();
  const [hypo, setHypo] = useState<HypoResult | null>(null);
  const [answer, setAnswer] = useState("");
  const [reveal, setReveal] = useState(false);
  const [grading, setGrading] = useState(false);
  const [grade, setGrade] = useState<HypoEvalResult | null>(null);

  async function gen() {
    setLoading(true); setErr(null); setHypo(null); setAnswer(""); setReveal(false); setGrade(null);
    try { setHypo(await studyHypo(topic.trim() || undefined)); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }
  async function gradeIt() {
    if (!hypo || !answer.trim()) return;
    setGrading(true);
    try { setGrade(await studyHypoEvaluate(hypo.facts, answer.trim())); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setGrading(false); }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <input className="min-w-[240px] flex-1 rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Doctrinal area/topic — e.g. FDCPA third-party contact (blank = consumer protection)"
          value={topic} onChange={(e) => setTopic(e.target.value)} />
        <button onClick={() => void gen()} disabled={loading}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {loading ? "Writing hypo…" : "New hypo"}
        </button>
      </div>
      {loading && <Spinner label="Writing a fact pattern…" />}
      {err && <ErrBox msg={err} />}
      {hypo && hypo.note && <InfoBox msg={hypo.note} />}
      {hypo && hypo.facts && (
        <div className="space-y-3">
          <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">Fact pattern · {hypo.area}</div>
            <p className="mt-1 whitespace-pre-wrap text-slate-700">{hypo.facts}</p>
          </div>
          <textarea className="h-28 w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Spot the legal issues — list what you'd analyze…" value={answer} onChange={(e) => setAnswer(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <button onClick={() => void gradeIt()} disabled={grading || !answer.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {grading ? "Grading…" : "Grade my answer"}
            </button>
            <button onClick={() => setReveal((r) => !r)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50">
              {reveal ? "Hide" : "Reveal"} model answer
            </button>
          </div>
          {grade && (
            <div className="rounded-lg bg-slate-50 p-3 text-sm">
              <div className="text-lg font-semibold text-indigo-700">Score: {grade.score_0_100}/100</div>
              {grade.found.length > 0 && <p className="mt-1 text-emerald-700">✓ Found: {grade.found.join("; ")}</p>}
              {grade.missed.length > 0 && <p className="mt-1 text-amber-700">○ Missed: {grade.missed.join("; ")}</p>}
              <p className="mt-1 text-slate-700">{grade.feedback}</p>
            </div>
          )}
          {reveal && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm">
              <div className="text-xs font-semibold uppercase tracking-wide text-indigo-500">Model issues</div>
              <ul className="mt-1 space-y-2">
                {hypo.model_issues.map((it, i) => (
                  <li key={i}>
                    <span className="font-medium text-slate-800">{it.issue}</span>
                    {it.rule && <span className="text-slate-600"> — Rule: {it.rule}</span>}
                    {it.analysis && <span className="text-slate-600"> — {it.analysis}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-[11px] text-slate-400">{hypo.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

// ---------------- Bluebook Cite ----------------
function CiteFormatter() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const { err, setErr } = useErr();
  const [res, setRes] = useState<CiteResult | null>(null);

  async function go() {
    if (!input.trim()) return;
    setLoading(true); setErr(null); setRes(null);
    try { setRes(await studyCite(input.trim())); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }

  return (
    <div className="space-y-3">
      <input className="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder="Rough citation / case name / statute — e.g. heintz v jenkins 514 us 291 1995"
        value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void go()} />
      <div className="flex gap-2">
        <button onClick={() => void go()} disabled={loading || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {loading ? "Formatting…" : "Format (Bluebook)"}
        </button>
        <button onClick={() => { setInput(""); setRes(null); setErr(null); }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50">Clear</button>
      </div>
      {loading && <Spinner label="Formatting citation…" />}
      {err && <ErrBox msg={err} />}
      {res && (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <div className="rounded bg-slate-50 p-3 font-serif text-slate-800">{res.bluebook}</div>
          <div className="text-xs text-slate-500">type: {res.type}</div>
          {Object.keys(res.components || {}).length > 0 && (
            <dl className="text-xs text-slate-600">
              {Object.entries(res.components).map(([k, v]) => (
                <div key={k} className="flex gap-1"><dt className="font-semibold">{k}:</dt><dd>{v}</dd></div>
              ))}
            </dl>
          )}
          {res.notes && <p className="text-xs text-amber-700">{res.notes}</p>}
          <p className="text-[11px] text-slate-400">{res.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

// ---------------- Related authorities + Outline ----------------
function ResearchAids() {
  const [simText, setSimText] = useState("");
  const [simLoading, setSimLoading] = useState(false);
  const [sim, setSim] = useState<SimilarResult | null>(null);
  const { err: simErr, setErr: setSimErr } = useErr();

  const [topic, setTopic] = useState("");
  const [outLoading, setOutLoading] = useState(false);
  const [out, setOut] = useState<OutlineResult | null>(null);
  const { err: outErr, setErr: setOutErr } = useErr();

  async function findSimilar() {
    if (!simText.trim()) return;
    setSimLoading(true); setSimErr(null); setSim(null);
    try { setSim(await studySimilar(simText.trim())); }
    catch (e) { setSimErr(e instanceof Error ? e.message : String(e)); }
    finally { setSimLoading(false); }
  }
  async function buildOutline() {
    if (!topic.trim()) return;
    setOutLoading(true); setOutErr(null); setOut(null);
    try { setOut(await studyOutline(topic.trim())); }
    catch (e) { setOutErr(e instanceof Error ? e.message : String(e)); }
    finally { setOutLoading(false); }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-700">Related authorities (semantic search)</h3>
        <p className="text-xs text-slate-500">Paste a holding, issue, or passage to find the most similar cases in the corpus.</p>
        <textarea className="h-20 w-full resize-y rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="e.g. an attorney who regularly litigates consumer debt collection is a 'debt collector'"
          value={simText} onChange={(e) => setSimText(e.target.value)} />
        <button onClick={() => void findSimilar()} disabled={simLoading || !simText.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {simLoading ? "Searching…" : "Find related"}
        </button>
        {simErr && <ErrBox msg={simErr} />}
        {sim && sim.note && <p className="text-xs text-slate-500">{sim.note}</p>}
        {sim && sim.results.length > 0 && (
          <ul className="space-y-2">
            {sim.results.map((r, i) => (
              <li key={i} className="rounded-lg border border-slate-200 p-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-800">{r.citation || r.title || "source"}</span>
                  <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] text-indigo-600">rel {r.relevance}</span>
                </div>
                <p className="mt-1 text-xs text-slate-600">{r.snippet}</p>
                {r.url && <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-indigo-500 hover:underline">view source</a>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-700">Study outline</h3>
        <div className="flex flex-wrap gap-2">
          <input className="min-w-[240px] flex-1 rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Topic — e.g. Permissible purpose under the FCRA"
            value={topic} onChange={(e) => setTopic(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void buildOutline()} />
          <button onClick={() => void buildOutline()} disabled={outLoading || !topic.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
            {outLoading ? "Building…" : "Build outline"}
          </button>
        </div>
        {outErr && <ErrBox msg={outErr} />}
        {out && out.note && <InfoBox msg={out.note} />}
        {out && out.sections.length > 0 && (
          <div className="space-y-2 text-sm">
            {out.sections.map((s, i) => (
              <div key={i}>
                <h4 className="font-semibold text-slate-800">{s.heading}</h4>
                <ul className="list-disc pl-5 text-slate-700">
                  {s.points.map((p, j) => <li key={j}>{p}</li>)}
                </ul>
              </div>
            ))}
            <p className="text-[11px] text-slate-400">{out.disclaimer}</p>
          </div>
        )}
      </div>
    </div>
  );
}
