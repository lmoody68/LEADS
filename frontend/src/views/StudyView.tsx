import { useEffect, useState } from "react";
import {
  studyFlashcards,
  studyHypo,
  studyHypoEvaluate,
  studyCite,
  studySimilar,
  studyOutline,
  srsSave,
  srsDue,
  srsDecks,
  srsReview,
  srsStats,
  type FlashcardsResult,
  type HypoResult,
  type HypoEvalResult,
  type CiteResult,
  type SimilarResult,
  type OutlineResult,
  type SrsDueCard,
  type SrsDeck,
  type SrsStats,
} from "../lib/api";

type Mode = "flashcards" | "hypo" | "cite" | "research" | "review";

const MODES: { id: Mode; label: string }[] = [
  { id: "flashcards", label: "🃏 Flashcards" },
  { id: "review", label: "🔁 Review (SRS)" },
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
      {mode === "review" && <Review />}
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
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [deckName, setDeckName] = useState("");

  async function addToDeck() {
    if (!res || res.cards.length === 0) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const deck = (deckName.trim() || topic.trim() || "default").slice(0, 60);
      const r = await srsSave(res.cards, deck);
      setSaveMsg(`Added ${r.added} new card${r.added === 1 ? "" : "s"} to deck “${r.deck}” (${r.total} total). Study it in the Review tab.`);
    } catch (e) {
      setSaveMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

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
        <>
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="w-44 rounded-lg border border-slate-300 p-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder={`Deck (${topic.trim() || "default"})`}
              value={deckName}
              onChange={(e) => setDeckName(e.target.value)}
            />
            <button onClick={() => void addToDeck()} disabled={saving}
              className="rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50">
              {saving ? "Adding…" : "➕ Add to deck"}
            </button>
            {saveMsg && <span className="text-xs text-slate-500">{saveMsg}</span>}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {res.cards.map((c, i) => (
              <button key={i} onClick={() => setFlipped((f) => ({ ...f, [i]: !f[i] }))}
                className="min-h-[88px] rounded-lg border border-slate-200 bg-white p-3 text-left text-sm hover:border-indigo-300">
                <div className="text-[10px] uppercase tracking-wide text-slate-400">{flipped[i] ? "answer" : "term — tap to flip"}</div>
                <div className="mt-1 text-slate-800">{flipped[i] ? c.back : c.front}</div>
              </button>
            ))}
          </div>
        </>
      )}
      {res && <p className="text-[11px] text-slate-400">{res.disclaimer}</p>}
    </div>
  );
}

// ---------------- Review (spaced repetition) ----------------
function Review() {
  const [decks, setDecks] = useState<SrsDeck[]>([]);
  const [queue, setQueue] = useState<SrsDueCard[]>([]);
  const [idx, setIdx] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const { err, setErr } = useErr();
  const [done, setDone] = useState(false);
  const [stats, setStats] = useState<SrsStats | null>(null);
  const [deck, setDeck] = useState("all");

  async function refreshStats() {
    try {
      setStats(await srsStats());
    } catch {
      /* stats are best-effort */
    }
  }

  async function load(which?: string) {
    const target = which ?? deck;
    setLoading(true);
    setErr(null);
    setDone(false);
    try {
      const dk = await srsDecks();
      setDecks(dk.decks);
      const due = await srsDue(target, 100);
      setQueue(due.cards);
      setIdx(0);
      setRevealed(false);
      if (due.cards.length === 0) setDone(true);
      void refreshStats();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  // load on mount
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function rate(rating: "again" | "hard" | "good" | "easy") {
    const card = queue[idx];
    if (!card) return;
    try {
      await srsReview(card.deck || "default", card.id, rating);
    } catch {
      /* keep going; the schedule write is best-effort */
    }
    void refreshStats();
    if (idx + 1 >= queue.length) {
      setDone(true);
    } else {
      setIdx(idx + 1);
      setRevealed(false);
    }
  }

  const card = queue[idx];
  const totalDue = decks.find((d) => d.name === "default")?.due ?? queue.length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500">
          Spaced repetition (SM-2). Add cards from the Flashcards tab, then review them here — cards
          you find hard come back sooner.
        </p>
        <div className="flex items-center gap-2">
          {decks.length > 0 && (
            <select
              value={deck}
              onChange={(e) => {
                setDeck(e.target.value);
                void load(e.target.value);
              }}
              className="rounded-lg border border-slate-300 p-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            >
              <option value="all">All decks</option>
              {decks.map((d) => (
                <option key={d.name} value={d.name}>
                  {d.name} ({d.due} due)
                </option>
              ))}
            </select>
          )}
          <button onClick={() => void load()} className="text-xs text-indigo-600 hover:underline">Refresh</button>
        </div>
      </div>

      {stats && stats.total_cards > 0 && <StatsPanel s={stats} />}

      {decks.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          {decks.map((d) => (
            <span key={d.name} className="rounded bg-slate-100 px-2 py-1 text-slate-600">
              {d.name}: <strong>{d.due}</strong> due / {d.total}
            </span>
          ))}
        </div>
      )}
      {loading && <Spinner label="Loading your deck…" />}
      {err && <ErrBox msg={err} />}
      {!loading && decks.length === 0 && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          No review deck yet. Generate flashcards in the Flashcards tab and click “➕ Add to review deck”.
        </p>
      )}
      {!loading && done && decks.length > 0 && (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-center text-sm text-emerald-700">
          🎉 Nothing due right now. {totalDue === 0 ? "You're all caught up." : "Come back when cards are due."}
        </p>
      )}
      {!loading && !done && card && (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
          <div className="text-[10px] uppercase tracking-wide text-slate-400">
            Card {idx + 1} of {queue.length} due
          </div>
          <div className="min-h-[60px] text-lg font-medium text-slate-800">{card.front}</div>
          {revealed ? (
            <>
              <div className="rounded-lg bg-slate-50 p-3 text-slate-700">{card.back}</div>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => void rate("again")} className="rounded-lg bg-red-100 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-200">Again</button>
                <button onClick={() => void rate("hard")} className="rounded-lg bg-amber-100 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-200">Hard</button>
                <button onClick={() => void rate("good")} className="rounded-lg bg-emerald-100 px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-200">Good</button>
                <button onClick={() => void rate("easy")} className="rounded-lg bg-indigo-100 px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-200">Easy</button>
              </div>
            </>
          ) : (
            <button onClick={() => setRevealed(true)} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
              Show answer
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function StatsPanel({ s }: { s: SrsStats }) {
  const m = s.maturity;
  const matTotal = Math.max(1, m.new + m.learning + m.mature);
  const maxFc = Math.max(1, ...s.forecast.map((f) => f.due));
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="🔥 Streak" value={`${s.streak.current} day${s.streak.current === 1 ? "" : "s"}`}
          sub={`best ${s.streak.longest} · ${s.streak.reviewed_today ? "active today" : "review to keep it!"}`} />
        <Metric label="Reviews today" value={String(s.reviews_today)} sub={`${s.reviews_total} all-time`} />
        <Metric label="Due today" value={String(s.due_today)} sub={`${s.total_cards} cards total`} />
        <Metric label="Accuracy" value={s.accuracy_percent == null ? "—" : `${s.accuracy_percent}%`} sub="good + easy" />
      </div>

      {/* Maturity bar */}
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Card maturity</div>
        <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
          <div className="bg-sky-400" style={{ width: `${(m.new / matTotal) * 100}%` }} title={`new ${m.new}`} />
          <div className="bg-amber-400" style={{ width: `${(m.learning / matTotal) * 100}%` }} title={`learning ${m.learning}`} />
          <div className="bg-emerald-500" style={{ width: `${(m.mature / matTotal) * 100}%` }} title={`mature ${m.mature}`} />
        </div>
        <div className="mt-1 flex gap-3 text-[11px] text-slate-500">
          <span><span className="text-sky-500">●</span> new {m.new}</span>
          <span><span className="text-amber-500">●</span> learning {m.learning}</span>
          <span><span className="text-emerald-600">●</span> mature {m.mature}</span>
        </div>
      </div>

      {/* 7-day forecast */}
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Due — next 7 days</div>
        <div className="flex items-end gap-1.5">
          {s.forecast.map((f, i) => (
            <div key={f.date} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex h-12 w-full items-end">
                <div className="w-full rounded-t bg-indigo-400" style={{ height: `${(f.due / maxFc) * 100}%` }} title={`${f.due} due`} />
              </div>
              <span className="text-[9px] text-slate-400">{i === 0 ? "today" : f.date.slice(5)}</span>
              <span className="text-[9px] font-medium text-slate-500">{f.due}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-lg font-semibold text-slate-800">{value}</div>
      {sub && <div className="text-[10px] text-slate-400">{sub}</div>}
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
