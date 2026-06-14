import { useEffect, useState } from "react";
import {
  getCurriculum,
  getLesson,
  getQuiz,
  submitAnswer,
  getMastery,
  getScenario,
  evaluateApproach,
  type Curriculum,
  type CurriculumKc,
  type Lesson,
  type Quiz,
  type GradeResult,
  type MasteryProfile,
  type Scenario,
  type SandboxEvaluation,
} from "../lib/api";
import { ProviderBadge } from "../components/Sources";

type Mode = "learn" | "sandbox";

// Shared red/yellow/green helpers (N.O.R.M.A.-style readiness bands).
function barColor(color: string): string {
  if (color === "green") return "bg-emerald-500";
  if (color === "yellow") return "bg-amber-400";
  return "bg-red-400";
}
function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

// ── Mastery dashboard (per-KC P(known) bars, grouped by module) ──────────────
function MasteryDashboard({ profile }: { profile: MasteryProfile }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Overall readiness
            </p>
            <p className="text-2xl font-bold text-slate-800">
              {profile.overall_readiness_percent}%
            </p>
          </div>
          <div className="text-right text-xs text-slate-500">
            <p>
              {profile.mastered_kcs}/{profile.total_kcs} KCs mastered
            </p>
            <p>{profile.total_attempts} attempts</p>
          </div>
        </div>
        <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full ${barColor(profile.overall_color)}`}
            style={{ width: `${profile.overall_readiness_percent}%` }}
          />
        </div>
      </div>

      {profile.modules.map((m) => (
        <div key={m.module} className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-700">{m.module}</h4>
            <span className="text-xs text-slate-500">
              {m.mastered_count}/{m.kc_count} mastered
            </span>
          </div>
          <ul className="space-y-2">
            {m.kcs.map((k) => (
              <li key={k.kc_id}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-700">{k.name}</span>
                  <span className="font-mono text-slate-500">
                    P(known) {pct(k.p_mastery)}
                    {k.attempts > 0 ? ` · ${k.attempts} att` : ""}
                  </span>
                </div>
                <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full ${barColor(k.color)}`}
                    style={{ width: pct(k.p_mastery) }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

// ── LEARN mode: pick KC → lesson → quiz → feedback + mastery move ────────────
function LearnMode({
  curriculum,
  onMasteryChanged,
}: {
  curriculum: Curriculum;
  onMasteryChanged: () => void;
}) {
  const [activeKc, setActiveKc] = useState<CurriculumKc | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // answers + per-question grade result
  const [answers, setAnswers] = useState<Record<string, number | string>>({});
  const [grades, setGrades] = useState<Record<string, GradeResult>>({});

  async function pickKc(kc: CurriculumKc) {
    setActiveKc(kc);
    setLesson(null);
    setQuiz(null);
    setAnswers({});
    setGrades({});
    setError(null);
    setLoading("Generating lesson…");
    try {
      setLesson(await getLesson(kc.kc_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  async function startQuiz() {
    if (!activeKc) return;
    setError(null);
    setQuiz(null);
    setGrades({});
    setAnswers({});
    setLoading("Generating quiz…");
    try {
      setQuiz(await getQuiz(activeKc.kc_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  async function grade(questionId: string) {
    if (!quiz) return;
    const ans = answers[questionId];
    if (ans === undefined || ans === "") return;
    setError(null);
    try {
      const res = await submitAnswer(quiz.kc_id, questionId, ans);
      setGrades((g) => ({ ...g, [questionId]: res }));
      onMasteryChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function clearLesson() {
    setActiveKc(null);
    setLesson(null);
    setQuiz(null);
    setAnswers({});
    setGrades({});
    setError(null);
  }

  return (
    <div className="grid gap-5 md:grid-cols-[260px_1fr]">
      {/* KC picker */}
      <aside className="space-y-3">
        {curriculum.modules.map((m) => (
          <div key={m.module}>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {m.module}
            </p>
            <ul className="space-y-1">
              {m.kcs.map((kc) => (
                <li key={kc.kc_id}>
                  <button
                    onClick={() => void pickKc(kc)}
                    className={`w-full rounded-md px-2.5 py-1.5 text-left text-sm transition ${
                      activeKc?.kc_id === kc.kc_id
                        ? "bg-indigo-50 font-medium text-indigo-700"
                        : "text-slate-600 hover:bg-slate-50"
                    }`}
                    title={kc.description}
                  >
                    {kc.name}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </aside>

      {/* Lesson + quiz pane */}
      <section className="space-y-4">
        {loading && (
          <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
            {loading}
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {!activeKc && !loading && (
          <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
            Pick a knowledge component on the left to generate an adaptive lesson, then take a
            quiz. Your mastery updates with Bayesian Knowledge Tracing.
          </p>
        )}

        {lesson && (
          <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {lesson.module}
                </p>
                <h3 className="text-lg font-semibold text-slate-800">{lesson.kc_name}</h3>
              </div>
              <ProviderBadge provider={lesson.provider} />
            </div>
            <p className="text-sm leading-relaxed text-slate-700">{lesson.summary}</p>
            {lesson.key_points.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Key points
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {lesson.key_points.map((k, i) => (
                    <li key={i}>{k}</li>
                  ))}
                </ul>
              </div>
            )}
            {lesson.worked_example && (
              <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Worked example
                </p>
                <p className="mt-1">{lesson.worked_example}</p>
              </div>
            )}
            {lesson.pitfalls.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">
                  Pitfalls
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {lesson.pitfalls.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
            {lesson.takeaway && (
              <p className="rounded-md border border-indigo-100 bg-indigo-50 p-2.5 text-sm font-medium text-indigo-800">
                💡 {lesson.takeaway}
              </p>
            )}
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => void startQuiz()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                {quiz ? "New quiz" : "Take the quiz"}
              </button>
              <button
                onClick={clearLesson}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {quiz && (
          <div className="space-y-4">
            {quiz.questions.map((q, idx) => {
              const g = grades[q.question_id];
              return (
                <div
                  key={q.question_id}
                  className="rounded-lg border border-slate-200 bg-white p-4"
                >
                  <p className="text-sm font-medium text-slate-800">
                    {idx + 1}. {q.prompt}
                  </p>
                  {q.type === "mc" && q.options ? (
                    <ul className="mt-2 space-y-1.5">
                      {q.options.map((opt, oi) => (
                        <li key={oi}>
                          <label
                            className={`flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm ${
                              answers[q.question_id] === oi
                                ? "border-indigo-300 bg-indigo-50"
                                : "border-slate-200 hover:bg-slate-50"
                            }`}
                          >
                            <input
                              type="radio"
                              name={q.question_id}
                              checked={answers[q.question_id] === oi}
                              disabled={!!g}
                              onChange={() =>
                                setAnswers((a) => ({ ...a, [q.question_id]: oi }))
                              }
                              className="mt-0.5"
                            />
                            <span className="text-slate-700">{opt}</span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <textarea
                      className="mt-2 w-full resize-y rounded-md border border-slate-300 p-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      rows={3}
                      placeholder="Type your short answer…"
                      disabled={!!g}
                      value={(answers[q.question_id] as string) || ""}
                      onChange={(e) =>
                        setAnswers((a) => ({ ...a, [q.question_id]: e.target.value }))
                      }
                    />
                  )}

                  {!g ? (
                    <button
                      onClick={() => void grade(q.question_id)}
                      disabled={
                        answers[q.question_id] === undefined ||
                        answers[q.question_id] === ""
                      }
                      className="mt-2 rounded-lg bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Submit answer
                    </button>
                  ) : (
                    <div
                      className={`mt-3 rounded-md border p-3 text-sm ${
                        g.correct
                          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                          : "border-amber-200 bg-amber-50 text-amber-800"
                      }`}
                    >
                      <p className="font-semibold">
                        {g.correct ? "✓ Correct" : "✗ Not quite"}
                      </p>
                      <p className="mt-1">{g.feedback}</p>
                      <p className="mt-2 font-mono text-xs text-slate-600">
                        P(known): {pct(g.mastery_before)} → {pct(g.mastery_after)}{" "}
                        {g.mastery_after > g.mastery_before ? "↑" : "↓"}
                      </p>
                      {g.recommended_next && (
                        <p className="mt-1 text-xs text-slate-600">
                          Recommended next: <strong>{g.recommended_next.name}</strong>
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

// ── SANDBOX mode: synthetic scenario → submit approach → evaluation ──────────
function SandboxMode({ onMasteryChanged }: { onMasteryChanged: () => void }) {
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [approach, setApproach] = useState("");
  const [evaluation, setEvaluation] = useState<SandboxEvaluation | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading("Generating a synthetic scenario…");
    setError(null);
    setScenario(null);
    setEvaluation(null);
    setApproach("");
    try {
      setScenario(await getScenario());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  async function evaluate() {
    if (!scenario || !approach.trim()) return;
    setLoading("Evaluating your methodology…");
    setError(null);
    try {
      const res = await evaluateApproach(scenario.scenario_id, approach.trim());
      setEvaluation(res);
      onMasteryChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  function clearAll() {
    setScenario(null);
    setApproach("");
    setEvaluation(null);
    setError(null);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => void generate()}
          disabled={!!loading}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {scenario ? "New scenario" : "Generate scenario"}
        </button>
        {scenario && (
          <button
            onClick={clearAll}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Clear
          </button>
        )}
      </div>

      {loading && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
          {loading}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!scenario && !loading && (
        <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
          Generate a clearly-synthetic practice scenario, write your research approach, and the
          tutor evaluates your methodology (triangulation, source credibility, compliance,
          dead-end handling) — then updates your mastery.
        </p>
      )}

      {scenario && (
        <div className="space-y-3">
          <div className="rounded-md border border-amber-300 bg-amber-50 p-2.5 text-xs font-medium text-amber-800">
            {scenario.synthetic_banner}
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-lg font-semibold text-slate-800">{scenario.title}</h3>
              <ProviderBadge provider={scenario.provider} />
            </div>
            <p className="mt-1 text-sm text-slate-700">{scenario.objective}</p>
            <p className="mt-2 text-xs text-slate-500">
              <strong>Lawful purpose:</strong> {scenario.lawful_purpose}
            </p>
            {scenario.known_facts.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Known facts (fictional)
                </p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
                  {scenario.known_facts.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
            {scenario.available_sources.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Available sources (fictional)
                </p>
                <ul className="mt-1 space-y-1 text-sm text-slate-700">
                  {scenario.available_sources.map((s, i) => (
                    <li key={i}>
                      <span className="font-medium">{s.name}</span>{" "}
                      <span className="text-xs text-slate-500">
                        [{s.type} · {s.reliability} reliability]
                      </span>
                      {s.note && <span className="text-slate-600"> — {s.note}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">
              Your research approach (methodology):
            </label>
            <textarea
              className="w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              rows={5}
              placeholder="Describe how you would approach this: which sources first, how you'd triangulate, how you'd judge credibility, how you'd stay within the lawful purpose, and how you'd handle dead-ends…"
              value={approach}
              onChange={(e) => setApproach(e.target.value)}
              disabled={!!evaluation}
            />
            {!evaluation && (
              <button
                onClick={() => void evaluate()}
                disabled={!approach.trim() || !!loading}
                className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
              >
                Evaluate my approach
              </button>
            )}
          </div>
        </div>
      )}

      {evaluation && (
        <div className="space-y-3">
          <div
            className={`rounded-lg border p-4 ${
              evaluation.verdict === "pass"
                ? "border-emerald-200 bg-emerald-50"
                : "border-amber-200 bg-amber-50"
            }`}
          >
            <div className="flex items-center justify-between">
              <p className="text-lg font-bold text-slate-800">
                {evaluation.verdict === "pass" ? "✓ Pass" : "Needs work"} · {evaluation.overall}
                /100
              </p>
              <ProviderBadge provider={evaluation.provider} />
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {Object.entries(evaluation.scores).map(([dim, sc]) => (
                <div key={dim}>
                  <div className="flex justify-between text-xs text-slate-600">
                    <span>{dim.replace(/_/g, " ")}</span>
                    <span className="font-mono">{sc}</span>
                  </div>
                  <div className="mt-0.5 h-2 w-full overflow-hidden rounded-full bg-white">
                    <div
                      className={`h-full ${
                        sc >= 75 ? "bg-emerald-500" : sc >= 50 ? "bg-amber-400" : "bg-red-400"
                      }`}
                      style={{ width: `${sc}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {evaluation.did_well.length > 0 && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                ✓ Did well
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-emerald-800">
                {evaluation.did_well.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          )}
          {evaluation.could_improve.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Could improve
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
                {evaluation.could_improve.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          )}
          {evaluation.compliance_flags.length > 0 && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-red-700">
                ⚠ Compliance flags
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-red-800">
                {evaluation.compliance_flags.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          )}
          {evaluation.ideal_approach.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Reference approach
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
                {evaluation.ideal_approach.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600">
            <p className="font-semibold uppercase tracking-wide text-slate-500">
              Mastery updates
            </p>
            <ul className="mt-1 space-y-0.5 font-mono">
              {evaluation.mastery_updates.map((u) => (
                <li key={u.kc_id}>
                  {u.kc_name}: {pct(u.mastery_before)} → {pct(u.mastery_after)}{" "}
                  {u.mastery_after > u.mastery_before ? "↑" : "↓"}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tutor view shell (Learn / Sandbox + live mastery dashboard) ──────────────
export default function TutorView() {
  const [mode, setMode] = useState<Mode>("learn");
  const [curriculum, setCurriculum] = useState<Curriculum | null>(null);
  const [profile, setProfile] = useState<MasteryProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshMastery() {
    try {
      setProfile(await getMastery());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    getCurriculum()
      .then(setCurriculum)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    void refreshMastery();
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Investigative Methodology Tutor</h2>
        <p className="text-sm text-slate-500">
          Adaptive lessons + quizzes across 5 modules, with{" "}
          <strong>Bayesian Knowledge Tracing</strong> mastery (ported from N.O.V.A.S.). The
          Practice Sandbox uses <strong>clearly-synthetic, fictional</strong> scenarios — no real
          people, no real PII.
        </p>
      </div>

      <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
        <button
          onClick={() => setMode("learn")}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            mode === "learn" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600"
          }`}
        >
          Learn
        </button>
        <button
          onClick={() => setMode("sandbox")}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            mode === "sandbox" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600"
          }`}
        >
          Practice Sandbox
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>
          {mode === "learn" ? (
            curriculum ? (
              <LearnMode curriculum={curriculum} onMasteryChanged={refreshMastery} />
            ) : (
              <p className="text-sm text-slate-400">Loading curriculum…</p>
            )
          ) : (
            <SandboxMode onMasteryChanged={refreshMastery} />
          )}
        </div>
        <aside>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Mastery dashboard
          </p>
          {profile ? (
            <MasteryDashboard profile={profile} />
          ) : (
            <p className="text-sm text-slate-400">No attempts yet.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
