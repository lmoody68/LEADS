import { useRef, useState } from "react";
import {
  casefileAsk,
  casefilePatterns,
  casefileRedaction,
  casefileRelationships,
  casefileTimeline,
  casefileUpload,
  type AnswerResponse,
  type Entities,
  type PatternsResponse,
  type RedactionResponse,
  type RelationshipsResponse,
  type TimelineResponse,
} from "../lib/api";
import { ProviderBadge, Sources } from "../components/Sources";

const ENTITY_LABELS: Record<keyof Entities, string> = {
  people: "People",
  organizations: "Organizations",
  locations: "Locations",
  dates: "Dates",
  legal_citations: "Legal citations",
};

type Tab = "entities" | "ask" | "relationships" | "timeline" | "patterns" | "redaction";

const TABS: { id: Tab; label: string }[] = [
  { id: "entities", label: "Entities" },
  { id: "ask", label: "Ask" },
  { id: "relationships", label: "Relationships" },
  { id: "timeline", label: "Timeline" },
  { id: "patterns", label: "Patterns" },
  { id: "redaction", label: "Redaction" },
];

function EntityOutline({ entities }: { entities: Entities }) {
  const keys = Object.keys(ENTITY_LABELS) as (keyof Entities)[];
  const hasAny = keys.some((k) => entities[k]?.length);
  if (!hasAny) {
    return <p className="text-sm text-slate-500">No entities extracted.</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {keys.map((k) => (
        <div key={k} className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {ENTITY_LABELS[k]}
          </p>
          {entities[k]?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {entities[k].map((v, i) => (
                <span
                  key={i}
                  className="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
                >
                  {v}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400">—</p>
          )}
        </div>
      ))}
    </div>
  );
}

function StateMessage({
  loading,
  error,
  empty,
  emptyText,
}: {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyText: string;
}) {
  if (loading)
    return <p className="text-sm text-slate-500">Analyzing the document collection…</p>;
  if (error)
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        {error}
      </div>
    );
  if (empty) return <p className="text-sm text-slate-500">{emptyText}</p>;
  return null;
}

export default function DocumentView() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [entities, setEntities] = useState<Entities | null>(null);
  const [chunks, setChunks] = useState<number>(0);
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const [tab, setTab] = useState<Tab>("entities");

  // Ask
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<AnswerResponse | null>(null);

  // Phase 5 analyses (lazily loaded per tab, cached in state)
  const [rels, setRels] = useState<RelationshipsResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [patterns, setPatterns] = useState<PatternsResponse | null>(null);
  const [redaction, setRedaction] = useState<RedactionResponse | null>(null);
  const [busy, setBusy] = useState<Tab | null>(null);
  const [tabError, setTabError] = useState<string | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const res = await casefileUpload(file, collectionId ?? undefined);
      setCollectionId(res.collection_id);
      setEntities(res.entities);
      setChunks(res.chunks);
      setNote(res.note || "");
      // A new upload changes the collection — drop any computed analyses.
      setRels(null);
      setTimeline(null);
      setPatterns(null);
      setRedaction(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function onAsk() {
    const q = question.trim();
    if (!q || !collectionId) return;
    setAsking(true);
    setError(null);
    setResult(null);
    try {
      setResult(await casefileAsk(q, collectionId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAsking(false);
    }
  }

  async function load(target: Tab, refresh = false) {
    if (!collectionId) return;
    setBusy(target);
    setTabError(null);
    try {
      if (target === "relationships")
        setRels(await casefileRelationships(collectionId, refresh));
      else if (target === "timeline")
        setTimeline(await casefileTimeline(collectionId, refresh));
      else if (target === "patterns")
        setPatterns(await casefilePatterns(collectionId, refresh));
      else if (target === "redaction")
        setRedaction(await casefileRedaction(collectionId, true));
    } catch (e) {
      setTabError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function switchTab(t: Tab) {
    setTab(t);
    setTabError(null);
    // Lazy-load analysis tabs the first time they're opened.
    if (t === "relationships" && !rels) load("relationships");
    else if (t === "timeline" && !timeline) load("timeline");
    else if (t === "patterns" && !patterns) load("patterns");
    else if (t === "redaction" && !redaction) load("redaction");
  }

  function onClear() {
    setCollectionId(null);
    setEntities(null);
    setChunks(0);
    setNote("");
    setQuestion("");
    setResult(null);
    setError(null);
    setRels(null);
    setTimeline(null);
    setPatterns(null);
    setRedaction(null);
    setTabError(null);
    setTab("entities");
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Document Analysis</h2>
        <p className="text-sm text-slate-500">
          Upload document(s) you lawfully possess. They are analyzed locally — no scraping, no
          PII harvesting. Extract entities, map relationships, build a timeline, surface
          cross-document patterns, and flag sensitive PII to redact before sharing.
        </p>
      </div>

      <div
        className="rounded-lg border-2 border-dashed border-slate-300 p-6 text-center"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFile(e.dataTransfer.files?.[0]);
        }}
      >
        <p className="text-sm text-slate-500">
          Drag &amp; drop a PDF, .txt or .md file here, or
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,.md,.markdown,.text"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <div className="mt-2 flex justify-center gap-2">
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {uploading
              ? "Uploading…"
              : collectionId
              ? "Add another document"
              : "Choose file"}
          </button>
          {collectionId && (
            <button
              onClick={onClear}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              Clear
            </button>
          )}
        </div>
        {collectionId && (
          <p className="mt-2 text-xs text-slate-500">
            Add more files to this collection to analyze across documents.
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {note && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {note}
        </div>
      )}

      {collectionId && entities && (
        <div className="space-y-4">
          <p className="text-xs text-slate-500">
            Collection <span className="font-mono">{collectionId}</span> · {chunks} chunk(s)
            indexed
          </p>

          {/* Sub-tabs */}
          <div className="flex flex-wrap gap-1 border-b border-slate-200">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => switchTab(t.id)}
                className={`-mb-px rounded-t-lg border-b-2 px-3 py-2 text-sm font-medium ${
                  tab === t.id
                    ? "border-indigo-600 text-indigo-700"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Entities */}
          {tab === "entities" && (
            <div>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Entity outline
              </h3>
              <EntityOutline entities={entities} />
            </div>
          )}

          {/* Ask */}
          {tab === "ask" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">
                Ask about this document collection
              </label>
              <textarea
                className="w-full resize-y rounded-lg border border-slate-300 p-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                rows={2}
                placeholder="e.g. What dates and parties are mentioned?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  onClick={onAsk}
                  disabled={asking || !question.trim()}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {asking ? "Asking…" : "Ask"}
                </button>
                {(question || result) && (
                  <button
                    onClick={() => {
                      setQuestion("");
                      setResult(null);
                    }}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  >
                    Clear
                  </button>
                )}
              </div>
              {result && (
                <div className="space-y-4 pt-2">
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
          )}

          {/* Relationships */}
          {tab === "relationships" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Relationship map
                </h3>
                <div className="flex items-center gap-2">
                  {rels && <ProviderBadge provider={rels.provider} />}
                  <button
                    onClick={() => load("relationships", true)}
                    disabled={busy === "relationships"}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {busy === "relationships" ? "Recomputing…" : "Recompute"}
                  </button>
                </div>
              </div>
              <StateMessage
                loading={busy === "relationships"}
                error={tabError}
                empty={!!rels && rels.relationships.length === 0}
                emptyText={rels?.note || "No relationships extracted."}
              />
              {rels && rels.relationships.length > 0 && (
                <RelationshipList rels={rels} />
              )}
            </div>
          )}

          {/* Timeline */}
          {tab === "timeline" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Chronology
                </h3>
                <div className="flex items-center gap-2">
                  {timeline && <ProviderBadge provider={timeline.provider} />}
                  <button
                    onClick={() => load("timeline", true)}
                    disabled={busy === "timeline"}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {busy === "timeline" ? "Recomputing…" : "Recompute"}
                  </button>
                </div>
              </div>
              <StateMessage
                loading={busy === "timeline"}
                error={tabError}
                empty={!!timeline && timeline.events.length === 0}
                emptyText={timeline?.note || "No dated events found."}
              />
              {timeline && timeline.events.length > 0 && (
                <ol className="relative space-y-4 border-l-2 border-slate-200 pl-5">
                  {timeline.events.map((ev, i) => (
                    <li key={i} className="relative">
                      <span className="absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-indigo-500 bg-white" />
                      <p className="text-sm font-semibold text-indigo-700">{ev.date}</p>
                      <p className="text-sm text-slate-800">{ev.event}</p>
                      <p className="mt-0.5 text-xs text-slate-400">
                        <span className="font-mono">{ev.source_doc}</span>
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}

          {/* Patterns */}
          {tab === "patterns" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Cross-document insights
                </h3>
                <div className="flex items-center gap-2">
                  {patterns && <ProviderBadge provider={patterns.provider} />}
                  <button
                    onClick={() => load("patterns", true)}
                    disabled={busy === "patterns"}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {busy === "patterns" ? "Recomputing…" : "Recompute"}
                  </button>
                </div>
              </div>
              <StateMessage
                loading={busy === "patterns"}
                error={tabError}
                empty={!!patterns && patterns.observations.length === 0}
                emptyText={patterns?.note || "No cross-document patterns found."}
              />
              {patterns && patterns.observations.length > 0 && (
                <div className="space-y-2">
                  {patterns.observations.map((o, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-slate-200 bg-white p-3"
                    >
                      <div className="mb-1 flex items-center gap-2">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                            o.type === "discrepancy"
                              ? "bg-rose-100 text-rose-700"
                              : "bg-emerald-100 text-emerald-700"
                          }`}
                        >
                          {o.type}
                        </span>
                      </div>
                      <p className="text-sm text-slate-800">{o.observation}</p>
                      {o.supporting_docs.length > 0 && (
                        <p className="mt-1 text-xs text-slate-400">
                          {o.supporting_docs.map((d, j) => (
                            <span key={j} className="mr-2 font-mono">
                              {d}
                            </span>
                          ))}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Redaction */}
          {tab === "redaction" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Suggested redactions
                </h3>
                <div className="flex items-center gap-2">
                  {redaction && <ProviderBadge provider={redaction.provider} />}
                  <button
                    onClick={() => load("redaction", true)}
                    disabled={busy === "redaction"}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {busy === "redaction" ? "Scanning…" : "Rescan"}
                  </button>
                </div>
              </div>
              <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800">
                {redaction?.privacy_note ||
                  "This flags sensitive PII so you can redact it BEFORE sharing a document. It is a privacy-protecting feature — your files stay local."}
              </div>
              <StateMessage
                loading={busy === "redaction"}
                error={tabError}
                empty={!!redaction && redaction.redactions.length === 0}
                emptyText={redaction?.note || "No sensitive PII detected."}
              />
              {redaction && redaction.redactions.length > 0 && (
                <>
                  <p className="text-xs text-slate-500">
                    {redaction.deterministic_count} found by deterministic scan
                    {redaction.llm_count > 0
                      ? `, ${redaction.llm_count} more by AI`
                      : ""}
                    .
                  </p>
                  <div className="space-y-2">
                    {redaction.redactions.map((r, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-slate-200 bg-white p-3"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-rose-700">
                                {r.type}
                              </span>
                              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-500">
                                {r.detected_by}
                              </span>
                            </div>
                            <p className="mt-1 break-all font-mono text-sm text-slate-800">
                              {r.text}
                            </p>
                            <p className="mt-0.5 text-xs text-slate-500">{r.reason}</p>
                          </div>
                          <span className="shrink-0 rounded bg-rose-50 px-2 py-0.5 font-mono text-xs text-rose-700">
                            {r.suggested_redaction}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-400">
                          <span className="font-mono">{r.source_doc}</span>
                        </p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RelationshipList({ rels }: { rels: RelationshipsResponse }) {
  // Group relationships by their "from" entity for a clean, library-free display.
  const grouped = new Map<string, RelationshipsResponse["relationships"]>();
  for (const r of rels.relationships) {
    const arr = grouped.get(r.from) ?? [];
    arr.push(r);
    grouped.set(r.from, arr);
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {rels.entities.map((e, i) => (
          <span
            key={i}
            className="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
          >
            {e}
          </span>
        ))}
      </div>
      {[...grouped.entries()].map(([from, edges]) => (
        <div key={from} className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="mb-1 text-sm font-semibold text-slate-800">{from}</p>
          <ul className="space-y-1.5">
            {edges.map((r, i) => (
              <li key={i} className="text-sm text-slate-700">
                <span className="text-slate-400">→ </span>
                <span className="font-medium text-indigo-700">{r.type}</span>{" "}
                <span className="text-slate-800">{r.to}</span>
                {r.evidence_snippet && (
                  <p className="ml-4 mt-0.5 border-l-2 border-slate-200 pl-2 text-xs italic text-slate-500">
                    “{r.evidence_snippet}”
                    {r.source_doc && (
                      <span className="ml-1 not-italic font-mono text-slate-400">
                        — {r.source_doc}
                      </span>
                    )}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
