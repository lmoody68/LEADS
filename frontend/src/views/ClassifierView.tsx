import { useEffect, useState } from "react";
import {
  classifierStatus,
  classifierTrain,
  classifierPredict,
  type ClassifierMetrics,
  type PredictResult,
} from "../lib/api";

export default function ClassifierView() {
  const [metrics, setMetrics] = useState<ClassifierMetrics | null>(null);
  const [training, setTraining] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [text, setText] = useState("");
  const [predicting, setPredicting] = useState(false);
  const [pred, setPred] = useState<PredictResult | null>(null);
  const [predErr, setPredErr] = useState<string | null>(null);

  useEffect(() => {
    classifierStatus().then(setMetrics).catch(() => {});
  }, []);

  async function train() {
    setTraining(true);
    setErr(null);
    try {
      setMetrics(await classifierTrain());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setTraining(false);
    }
  }

  async function runPredict() {
    if (!text.trim()) return;
    setPredicting(true);
    setPredErr(null);
    setPred(null);
    try {
      setPred(await classifierPredict(text.trim()));
    } catch (e) {
      setPredErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPredicting(false);
    }
  }

  const trained = metrics?.trained;
  const pct = (v?: number) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Auxiliary Classifier</h2>
        <p className="text-sm text-slate-500">
          A supervised-ML showcase: the corpus's <strong>MiniLM sentence embeddings</strong> feed a{" "}
          <strong>logistic-regression</strong> head that tags a document's <em>type</em>
          (statute / opinion / regulation / bill). Trained on the public corpus, evaluated on a
          held-out split + 5-fold cross-validation. Auxiliary metadata tagging — not legal advice.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => void train()}
          disabled={training}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {training ? "Training…" : trained ? "Retrain on current corpus" : "Train classifier"}
        </button>
        {metrics?.trained_at && (
          <span className="text-xs text-slate-400">last trained: {metrics.trained_at}</span>
        )}
      </div>

      {err && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{err}</div>}

      {!trained && !training && !err && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
          No model yet. Click <strong>Train classifier</strong> to train on the current corpus and
          see honest held-out + cross-validated metrics.
        </p>
      )}

      {/* Metrics */}
      {trained && metrics && (
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <div className="flex flex-wrap gap-2">
            <Stat label="Held-out accuracy" value={pct(metrics.holdout?.accuracy)} />
            <Stat label="Held-out macro-F1" value={pct(metrics.holdout?.macro_f1)} />
            <Stat
              label="CV macro-F1 (5-fold)"
              value={
                metrics.cross_val
                  ? `${pct(metrics.cross_val.macro_f1_mean)} ± ${(metrics.cross_val.macro_f1_std * 100).toFixed(1)}`
                  : "—"
              }
            />
            <Stat label="Samples" value={String(metrics.n_samples ?? "—")} />
            <Stat label="Features" value={`${metrics.n_features ?? "—"}-d`} />
          </div>
          <p className="text-xs text-slate-400">{metrics.model}</p>

          {/* Per-class table */}
          {metrics.per_class && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1 pr-3">class</th>
                    <th className="pr-3">precision</th>
                    <th className="pr-3">recall</th>
                    <th className="pr-3">F1</th>
                    <th className="pr-3">test support</th>
                    <th>train count</th>
                  </tr>
                </thead>
                <tbody className="text-slate-700">
                  {Object.entries(metrics.per_class).map(([c, v]) => (
                    <tr key={c} className="border-t border-slate-100">
                      <td className="py-1 pr-3 font-medium">{c}</td>
                      <td className="pr-3">{v.precision.toFixed(3)}</td>
                      <td className="pr-3">{v.recall.toFixed(3)}</td>
                      <td className="pr-3">{v.f1.toFixed(3)}</td>
                      <td className="pr-3">{v.support}</td>
                      <td>{v.train_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Confusion matrix */}
          {metrics.confusion && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Confusion matrix (rows = actual, cols = predicted)
              </h4>
              <div className="mt-1 overflow-x-auto">
                <table className="text-xs">
                  <thead>
                    <tr className="text-slate-400">
                      <th className="p-1"></th>
                      {metrics.confusion.labels.map((l) => (
                        <th key={l} className="p-1">{l}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.confusion.matrix.map((row, i) => (
                      <tr key={i}>
                        <td className="p-1 font-medium text-slate-500">{metrics.confusion!.labels[i]}</td>
                        {row.map((n, j) => (
                          <td
                            key={j}
                            className={`p-1 text-center ${i === j ? "font-semibold text-emerald-700" : "text-slate-500"}`}
                          >
                            {n}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {metrics.excluded_classes && Object.keys(metrics.excluded_classes).length > 0 && (
            <p className="text-xs text-slate-400">
              Excluded (too few samples, &lt;{metrics.min_per_class}):{" "}
              {Object.entries(metrics.excluded_classes)
                .map(([c, n]) => `${c} (${n})`)
                .join(", ")}
            </p>
          )}
          {metrics.disclaimer && <p className="text-[11px] text-slate-400">{metrics.disclaimer}</p>}
        </div>
      )}

      {/* Try it */}
      {trained && (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-slate-700">Try it</h3>
          <textarea
            className="h-24 w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Paste a sentence or passage and the classifier will predict its document type…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={() => void runPredict()}
              disabled={predicting || !text.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {predicting ? "Classifying…" : "Classify"}
            </button>
            <button
              onClick={() => {
                setText("");
                setPred(null);
                setPredErr(null);
              }}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              Clear
            </button>
          </div>
          {predErr && <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">{predErr}</div>}
          {pred && (
            <div className="rounded-lg bg-slate-50 p-3 text-sm">
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-semibold text-indigo-700">{pred.label}</span>
                <span className="text-xs text-slate-500">{(pred.confidence * 100).toFixed(1)}% confidence</span>
              </div>
              <div className="mt-2 space-y-1">
                {pred.probabilities.map((p) => (
                  <div key={p.label} className="flex items-center gap-2 text-xs">
                    <span className="w-24 text-slate-600">{p.label}</span>
                    <div className="h-2 flex-1 rounded bg-slate-200">
                      <div
                        className="h-2 rounded bg-indigo-500"
                        style={{ width: `${Math.round(p.confidence * 100)}%` }}
                      />
                    </div>
                    <span className="w-12 text-right text-slate-500">{(p.confidence * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-slate-400">{pred.disclaimer}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-indigo-50 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-indigo-400">{label}</div>
      <div className="text-sm font-semibold text-indigo-700">{value}</div>
    </div>
  );
}
