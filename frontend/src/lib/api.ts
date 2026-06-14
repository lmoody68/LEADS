const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8000/api";

export interface Citation {
  source_title: string;
  citation: string;
  section?: string;
  court?: string;
  date?: string;
  url?: string;
  doc_type?: string;
  legal_section?: string;
  snippet: string;
  score: number;
}

export interface IngestedCase {
  case_name: string;
  citation: string;
  court: string;
  date: string;
  url: string;
}

export interface RetrievalDebug {
  dense_top?: { citation: string; section: string; rel: number }[];
  bm25_top?: { citation: string; section: string; bm25: number }[];
  fused?: number;
  fused_top?: {
    citation: string;
    dense_rank: number | null;
    bm25_rank: number | null;
    rrf: number;
  }[];
}

export interface AnswerResponse {
  answer: string;
  citations: Citation[];
  provider: string;
  rewritten_query?: string;
  legal_issues?: string[];
  conflicts?: string[];
  followups?: string[];
  grounding?: string;
  retrieval?: RetrievalDebug;
  ingested?: IngestedCase[];
}

// --- Phase 2: Agentic Research Memo ----------------------------------------
export interface MemoSource {
  n: number;
  source_title: string;
  citation: string;
  doc_type?: string;
  court?: string;
  date?: string;
  url?: string;
  legal_section?: string;
  snippet: string;
  score: number;
  cited: boolean;
}

export interface MemoSection {
  title: string;
  body: string;
  confidence: "high" | "medium" | "low" | string;
}

export interface MemoResponse {
  question: string;
  deep: boolean;
  plan: string[];
  subq_sources: Record<string, number[]>;
  memo_markdown: string;
  sections: MemoSection[];
  sources: MemoSource[];
  findings: string[];
  conflicts: string[];
  gaps: string[];
  reviewer_notes: string[];
  citer_notes: string[];
  grounding: string;
  provider: string;
  providers: Record<string, string>;
  ingested: IngestedCase[];
}

export interface MemoHistoryEntry {
  question: string;
  deep: boolean;
  plan: string[];
  provider: string;
  n_sources: number;
  memo_markdown: string;
}

export function generateMemo(question: string, deep = true): Promise<MemoResponse> {
  return post<MemoResponse>("/memo", { question, deep });
}

export async function memoHistory(limit = 10): Promise<{ history: MemoHistoryEntry[]; total: number }> {
  const res = await fetch(`${API_BASE}/memo/history?limit=${limit}`);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

// --- Phase 3: Compliance & Ethics Advisor ----------------------------------
export interface ComplianceCitation {
  source_title: string;
  citation: string;
  url?: string;
  snippet: string;
}

export interface GoverningStatute {
  name: string;
  citation: string;
  why: string;
  url?: string;
}

export interface ComplianceResponse {
  scenario: string;
  permissible_purpose: { verdict: "yes" | "no" | "depends" | string; explanation: string };
  governing_statutes: GoverningStatute[];
  restrictions: string[];
  risk_flags: string[];
  compliant_alternatives: string[];
  citations: ComplianceCitation[];
  disclaimer: string;
  provider: string;
}

export function analyzeCompliance(scenario: string): Promise<ComplianceResponse> {
  return post<ComplianceResponse>("/compliance", { scenario });
}

// --- Phase 3: Source-Credibility Scorer -------------------------------------
export interface CredibilityDimension {
  name: string;
  weight: number;
  score_0_100: number;
  rationale: string;
}

export interface CredibilityResponse {
  source: {
    source_title: string;
    citation: string;
    doc_type?: string;
    court?: string;
    date?: string;
    url?: string;
    legal_section?: string;
  };
  dimensions: CredibilityDimension[];
  weighted_total: number;
  tier: "primary" | "secondary" | string;
  flags: string[];
  corroboration: { agreeing: string[]; conflicting: string[] };
  shepardize_heuristic: string;
  provider: string;
  error?: string;
}

export interface CredibilityInput {
  source_id?: string;
  title?: string;
  citation?: string;
  text?: string;
}

export function scoreCredibility(input: CredibilityInput): Promise<CredibilityResponse> {
  return post<CredibilityResponse>("/credibility", input);
}

export interface Entities {
  people: string[];
  organizations: string[];
  locations: string[];
  dates: string[];
  legal_citations: string[];
}

export interface UploadResponse {
  collection_id: string;
  chunks: number;
  entities: Entities;
  note?: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function ask(question: string, deep = true): Promise<AnswerResponse> {
  return post<AnswerResponse>("/ask", { question, deep });
}

export function casefileAsk(question: string, collectionId: string): Promise<AnswerResponse> {
  return post<AnswerResponse>("/casefile/ask", {
    question,
    collection_id: collectionId,
  });
}

export async function casefileUpload(
  file: File,
  collectionId?: string
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (collectionId) form.append("collection_id", collectionId);
  const res = await fetch(`${API_BASE}/casefile/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<UploadResponse>;
}
