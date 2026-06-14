import { useRef, useState } from "react";
import {
  casefileAsk,
  casefileUpload,
  type AnswerResponse,
  type Entities,
} from "../lib/api";
import { ProviderBadge, Sources } from "../components/Sources";

const ENTITY_LABELS: Record<keyof Entities, string> = {
  people: "People",
  organizations: "Organizations",
  locations: "Locations",
  dates: "Dates",
  legal_citations: "Legal citations",
};

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

export default function DocumentView() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [entities, setEntities] = useState<Entities | null>(null);
  const [chunks, setChunks] = useState<number>(0);
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<AnswerResponse | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const res = await casefileUpload(file);
      setCollectionId(res.collection_id);
      setEntities(res.entities);
      setChunks(res.chunks);
      setNote(res.note || "");
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

  function onClear() {
    setCollectionId(null);
    setEntities(null);
    setChunks(0);
    setNote("");
    setQuestion("");
    setResult(null);
    setError(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Document Analysis</h2>
        <p className="text-sm text-slate-500">
          Upload a document you lawfully possess. It is analyzed locally — no scraping, no
          PII harvesting. Entities are extracted and you can ask cited questions over it.
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
        <p className="text-sm text-slate-500">Drag &amp; drop a PDF, .txt or .md file here, or</p>
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
            {uploading ? "Uploading…" : "Choose file"}
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

          <div>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Entity outline
            </h3>
            <EntityOutline entities={entities} />
          </div>

          <div className="space-y-2 border-t border-slate-200 pt-4">
            <label className="text-sm font-medium text-slate-700">Ask about this document</label>
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
            </div>
          </div>

          {result && (
            <div className="space-y-4">
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
    </div>
  );
}
