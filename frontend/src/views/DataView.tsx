import { useEffect, useState } from "react";
import {
  ingestCourtListener,
  ingestGovinfo,
  ingestStatus,
  discoverDatasets,
  ingestDataset,
  type IngestResult,
  type IngestStatus,
  type DiscoverResponse,
  type DiscoveredDataset,
} from "../lib/api";

type Source = "courtlistener" | "govinfo";

export default function DataView() {
  // --- Corpus expansion state ---
  const [source, setSource] = useState<Source>("courtlistener");
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState(""); // jurisdiction (CL) or collection (govinfo)
  const [limit, setLimit] = useState(5);
  const [ingesting, setIngesting] = useState(false);
  const [ingestErr, setIngestErr] = useState<string | null>(null);
  const [ingestRes, setIngestRes] = useState<IngestResult | null>(null);

  // --- Status state ---
  const [status, setStatus] = useState<IngestStatus | null>(null);

  // --- Dataset discovery state ---
  const [dsQuery, setDsQuery] = useState("legal");
  const [discovering, setDiscovering] = useState(false);
  const [discoverErr, setDiscoverErr] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<DiscoverResponse | null>(null);
  const [addingId, setAddingId] = useState<string | null>(null);
  const [dsMsg, setDsMsg] = useState<string | null>(null);

  async function refreshStatus() {
    try {
      setStatus(await ingestStatus());
    } catch {
      /* status is best-effort */
    }
  }

  useEffect(() => {
    void refreshStatus();
  }, []);

  async function runIngest() {
    const q = query.trim();
    if (!q && source === "courtlistener") return;
    if (!q && !scope.trim()) return;
    setIngesting(true);
    setIngestErr(null);
    setIngestRes(null);
    try {
      const res =
        source === "courtlistener"
          ? await ingestCourtListener(q, limit, scope.trim() || undefined)
          : await ingestGovinfo(q, limit, scope.trim() || undefined);
      setIngestRes(res);
      await refreshStatus();
    } catch (e) {
      setIngestErr(e instanceof Error ? e.message : String(e));
    } finally {
      setIngesting(false);
    }
  }

  function clearIngest() {
    setQuery("");
    setScope("");
    setIngestRes(null);
    setIngestErr(null);
  }

  async function runDiscover(q: string) {
    const text = q.trim();
    if (!text) return;
    setDiscovering(true);
    setDiscoverErr(null);
    setDiscovered(null);
    setDsMsg(null);
    try {
      setDiscovered(await discoverDatasets(text, 12));
    } catch (e) {
      setDiscoverErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDiscovering(false);
    }
  }

  async function addDataset(d: DiscoveredDataset) {
    setAddingId(d.name);
    setDsMsg(null);
    try {
      const res = await ingestDataset(d.name, d.source);
      setDsMsg(`${d.name}: ${res.mode} — ${res.note}`);
      await refreshStatus();
    } catch (e) {
      setDsMsg(`${d.name}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setAddingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Data — Corpus Ingestion (admin)</h2>
        <p className="text-sm text-slate-500">
          Grow the legal corpus from <strong>official public-data APIs only</strong> (CourtListener,
          govinfo) and discover <strong>public legal datasets</strong> (Hugging Face Hub). No scraping,
          no bot-protection / rate-limit evasion, and <strong>no PII / people-search data</strong> — PII
          datasets are flagged and refused.
        </p>
      </div>

      {/* ---------------- Corpus stats ---------------- */}
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Corpus stats</h3>
          <button
            onClick={() => void refreshStatus()}
            className="text-xs text-indigo-600 hover:underline"
          >
            Refresh
          </button>
        </div>
        {status ? (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-md bg-indigo-50 px-2 py-1 font-medium text-indigo-700">
              {status.corpus_size} total chunks
            </span>
            {Object.entries(status.sources_breakdown).map(([k, v]) => (
              <span key={k} className="rounded-md bg-slate-100 px-2 py-1 text-slate-600">
                {k}: <strong>{v}</strong>
              </span>
            ))}
            {status.last_ingest && (
              <span className="text-xs text-slate-400">
                last: {status.last_ingest.source} +{status.last_ingest.added}
              </span>
            )}
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-400">Loading corpus stats…</p>
        )}
      </div>

      {/* ---------------- Corpus expansion ---------------- */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">Corpus expansion</h3>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSource("courtlistener")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              source === "courtlistener"
                ? "bg-indigo-600 text-white"
                : "border border-slate-300 text-slate-600 hover:bg-slate-50"
            }`}
          >
            CourtListener (case law)
          </button>
          <button
            onClick={() => setSource("govinfo")}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              source === "govinfo"
                ? "bg-indigo-600 text-white"
                : "border border-slate-300 text-slate-600 hover:bg-slate-50"
            }`}
          >
            govinfo (statutes / regs)
          </button>
        </div>

        <input
          className="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder={
            source === "courtlistener"
              ? "Topic / query — e.g. FDCPA attorney debt collection"
              : "Query — e.g. fair debt collection practices"
          }
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-2">
          <input
            className="w-56 rounded-lg border border-slate-300 p-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder={
              source === "courtlistener"
                ? "Jurisdiction (optional) — e.g. ca9, scotus"
                : "Collection (optional) — USCODE/CFR/PLAW/BILLS"
            }
            value={scope}
            onChange={(e) => setScope(e.target.value)}
          />
          <label className="text-sm text-slate-600">
            Limit
            <input
              type="number"
              min={1}
              max={25}
              value={limit}
              onChange={(e) => setLimit(Math.max(1, Math.min(25, Number(e.target.value) || 5)))}
              className="ml-2 w-16 rounded-lg border border-slate-300 p-1.5 text-sm"
            />
          </label>
          <button
            onClick={() => void runIngest()}
            disabled={ingesting || (!query.trim() && (source === "courtlistener" || !scope.trim()))}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {ingesting ? "Ingesting…" : "Ingest"}
          </button>
          <button
            onClick={clearIngest}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Clear
          </button>
        </div>

        {ingesting && (
          <div className="flex items-center gap-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-700">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
            Fetching from the official {source} API and embedding into the corpus…
          </div>
        )}

        {ingestErr && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {ingestErr}
          </div>
        )}

        {ingestRes && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm">
            <div className="flex flex-wrap gap-3 font-medium text-emerald-800">
              <span>added: {ingestRes.added}</span>
              <span>skipped (dupes): {ingestRes.skipped_dupes}</span>
              <span>
                corpus: {ingestRes.corpus_size_before} → {ingestRes.corpus_size_after}
              </span>
            </div>
            {ingestRes.note && <p className="mt-1 text-xs text-emerald-700">{ingestRes.note}</p>}
            {ingestRes.ingested.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-slate-600">
                {ingestRes.ingested.map((it, i) => (
                  <li key={i} className="truncate">
                    • {it.case_name || it.title} {it.citation ? `— ${it.citation}` : ""}
                    {it.package_id ? `— ${it.package_id}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* ---------------- Dataset discovery ---------------- */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">Dataset discovery (public legal datasets)</h3>
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="min-w-[220px] flex-1 rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Search legal datasets — e.g. legal, case law, pile-of-law, contracts"
            value={dsQuery}
            onChange={(e) => setDsQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void runDiscover(dsQuery)}
          />
          <button
            onClick={() => void runDiscover(dsQuery)}
            disabled={discovering || !dsQuery.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {discovering ? "Searching…" : "Search"}
          </button>
        </div>

        {discoverErr && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {discoverErr}
          </div>
        )}

        {dsMsg && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
            {dsMsg}
          </div>
        )}

        {discovered && (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">
              {discovered.results.length} result(s) from {discovered.sources_searched.join(", ")} ·{" "}
              {discovered.pii_flagged} flagged as PII-risk (refused).
            </p>
            <ul className="space-y-2">
              {discovered.results.map((d) => (
                <li
                  key={`${d.source}:${d.name}`}
                  className="rounded-lg border border-slate-200 p-3 text-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <a
                      href={d.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-indigo-700 hover:underline"
                    >
                      {d.name}
                    </a>
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
                        {d.source}
                      </span>
                      {d.is_pii_risk ? (
                        <span className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-semibold text-red-700">
                          ⚠ PII-risk — skipped
                        </span>
                      ) : (
                        <button
                          onClick={() => void addDataset(d)}
                          disabled={addingId === d.name}
                          className="rounded-md border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                        >
                          {addingId === d.name ? "Adding…" : "Add to corpus"}
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{d.description}</p>
                  <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slate-400">
                    <span>license: {d.license}</span>
                    <span>downloads: {d.downloads.toLocaleString()}</span>
                    {d.legal_relevant && <span className="text-indigo-500">legal-relevant</span>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!discovered && !discovering && !discoverErr && (
          <p className="rounded-lg border border-dashed border-slate-300 p-5 text-center text-sm text-slate-400">
            Search public legal-dataset repositories. Results show license + PII-risk flag; only
            non-PII public legal datasets can be added to the corpus.
          </p>
        )}
      </div>

      <p className="rounded-lg border border-slate-300 bg-slate-50 p-3 text-center text-xs text-slate-600">
        Official public-data APIs only · honest User-Agent + polite rate limits · no scraping / CAPTCHA
        / proxy / rate-limit evasion · public legal data only — no PII / people-search.
      </p>
    </div>
  );
}
