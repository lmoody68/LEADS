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

// --- Phase 4: BKT Tutor + Practice Sandbox ----------------------------------
// A stable per-browser session id keys the learner's BKT mastery profile.
const SESSION_KEY = "leads_session_id";
export function getSessionId(): string {
  let sid = localStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}

async function tutorPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": getSessionId() },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

async function tutorGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-Session-Id": getSessionId() },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export interface CurriculumKc {
  kc_id: string;
  name: string;
  description: string;
}
export interface CurriculumModule {
  module: string;
  kcs: CurriculumKc[];
}
export interface Curriculum {
  modules: CurriculumModule[];
  total_kcs: number;
  mastery_threshold: number;
}

export interface Lesson {
  kc_id: string;
  kc_name: string;
  module: string;
  summary: string;
  key_points: string[];
  worked_example: string;
  pitfalls: string[];
  takeaway: string;
  provider: string;
}

export interface QuizQuestion {
  question_id: string;
  type: "mc" | "short";
  prompt: string;
  options?: string[];
}
export interface Quiz {
  kc_id: string;
  kc_name: string;
  module: string;
  questions: QuizQuestion[];
  provider: string;
}

export interface RecommendedKc {
  kc_id: string;
  name: string;
  module: string;
  p_mastery: number;
  color: string;
}
export interface GradeResult {
  kc_id: string;
  question_id: string;
  type: "mc" | "short";
  correct: boolean;
  feedback: string;
  mastery_before: number;
  mastery_after: number;
  level: string;
  color: string;
  mastered: boolean;
  recommended_next: RecommendedKc | null;
  session_id: string;
}

export interface MasteryKc {
  kc_id: string;
  name: string;
  module: string;
  description: string;
  p_mastery: number;
  level: string;
  color: "red" | "yellow" | "green" | string;
  mastered: boolean;
  attempts: number;
  correct: number;
  incorrect: number;
}
export interface MasteryModule {
  module: string;
  avg_mastery: number;
  color: string;
  mastered_count: number;
  kc_count: number;
  kcs: MasteryKc[];
}
export interface MasteryProfile {
  session_id: string;
  overall_readiness_percent: number;
  overall_color: string;
  mastered_kcs: number;
  total_kcs: number;
  total_attempts: number;
  mastery_threshold: number;
  modules: MasteryModule[];
  recommended_next: RecommendedKc | null;
}

export function getCurriculum(): Promise<Curriculum> {
  return tutorGet<Curriculum>("/tutor/curriculum");
}
export function getLesson(kc: string): Promise<Lesson> {
  return tutorPost<Lesson>("/tutor/lesson", { kc });
}
export function getQuiz(kc: string): Promise<Quiz> {
  return tutorPost<Quiz>("/tutor/quiz", { kc });
}
export function submitAnswer(
  kc: string,
  questionId: string,
  answer: number | string
): Promise<GradeResult> {
  return tutorPost<GradeResult>("/tutor/answer", {
    kc,
    question_id: questionId,
    answer,
  });
}
export function getMastery(): Promise<MasteryProfile> {
  return tutorGet<MasteryProfile>("/tutor/mastery");
}

export interface SandboxSource {
  name: string;
  type: string;
  reliability: string;
  note: string;
}
export interface Scenario {
  scenario_id: string;
  synthetic: boolean;
  synthetic_banner: string;
  title: string;
  objective: string;
  lawful_purpose: string;
  known_facts: string[];
  available_sources: SandboxSource[];
  assessed_kcs: { kc_id: string; name: string }[];
  provider: string;
  session_id: string;
}

export interface SandboxMasteryUpdate {
  kc_id: string;
  kc_name: string;
  dimension: string;
  dimension_score: number;
  mastery_before: number;
  mastery_after: number;
  color: string;
}
export interface SandboxEvaluation {
  scenario_id: string;
  scores: Record<string, number>;
  overall: number;
  did_well: string[];
  could_improve: string[];
  compliance_flags: string[];
  verdict: "pass" | "needs_work" | string;
  ideal_approach: string[];
  mastery_updates: SandboxMasteryUpdate[];
  recommended_next: RecommendedKc | null;
  provider: string;
  session_id: string;
}

export function getScenario(): Promise<Scenario> {
  return tutorPost<Scenario>("/sandbox/scenario", {});
}
export function evaluateApproach(
  scenarioId: string,
  approach: string
): Promise<SandboxEvaluation> {
  return tutorPost<SandboxEvaluation>("/sandbox/evaluate", {
    scenario_id: scenarioId,
    approach,
  });
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

// --- Phase 5: Enhanced Document Analysis ------------------------------------
export interface Relationship {
  from: string;
  to: string;
  type: string;
  evidence_snippet: string;
  source_doc: string;
}
export interface RelationshipsResponse {
  collection_id: string;
  entities: string[];
  relationships: Relationship[];
  provider: string;
  note?: string;
}

export interface TimelineEvent {
  date: string;
  event: string;
  source_doc: string;
  snippet: string;
}
export interface TimelineResponse {
  collection_id: string;
  events: TimelineEvent[];
  provider: string;
  note?: string;
}

export interface PatternObservation {
  observation: string;
  type: "pattern" | "discrepancy" | string;
  supporting_docs: string[];
}
export interface PatternsResponse {
  collection_id: string;
  observations: PatternObservation[];
  provider: string;
  note?: string;
}

export interface RedactionItem {
  type: string;
  text: string;
  suggested_redaction: string;
  source_doc: string;
  reason: string;
  detected_by: "regex" | "llm" | string;
}
export interface RedactionResponse {
  collection_id: string;
  redactions: RedactionItem[];
  deterministic_count: number;
  llm_count: number;
  provider: string;
  note?: string;
  privacy_note: string;
}

async function casefileGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function casefileRelationships(
  collectionId: string,
  refresh = false
): Promise<RelationshipsResponse> {
  return casefileGet<RelationshipsResponse>(
    `/casefile/${collectionId}/relationships${refresh ? "?refresh=true" : ""}`
  );
}
export function casefileTimeline(
  collectionId: string,
  refresh = false
): Promise<TimelineResponse> {
  return casefileGet<TimelineResponse>(
    `/casefile/${collectionId}/timeline${refresh ? "?refresh=true" : ""}`
  );
}
export function casefilePatterns(
  collectionId: string,
  refresh = false
): Promise<PatternsResponse> {
  return casefileGet<PatternsResponse>(
    `/casefile/${collectionId}/patterns${refresh ? "?refresh=true" : ""}`
  );
}
export function casefileRedaction(
  collectionId: string,
  useLlm = true
): Promise<RedactionResponse> {
  return post<RedactionResponse>(`/casefile/${collectionId}/redaction`, {
    use_llm: useLlm,
  });
}
