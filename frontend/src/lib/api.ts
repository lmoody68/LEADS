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
