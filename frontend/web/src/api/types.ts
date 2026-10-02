// 后端接口的返回值类型，对照 app/api/*.py 手写。
// 以后可用 openapi-typescript 从 /openapi.json 自动生成。

/* ---------- 通用 ---------- */
export interface Paged<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

/* ---------- 作业 /api/jobs ---------- */
export type JobState = 'idle' | 'running' | 'ok' | 'failed' | 'stopped'
export interface Job {
  name: string
  title: string
  cmd: string
  needs: string
  heavy: boolean
  status: JobState
  pid: number | null
  started_at: string | null
  finished_at: string | null
  returncode: number | null
  log_mtime: string | null
  log?: string
}

/* ---------- 管理总览 /api/admin/overview ---------- */
export type ModuleStatus = 'ok' | 'attention' | 'missing' | 'error'
export interface ModuleCard {
  key: string
  title: string
  page: string
  lede: string
  status: ModuleStatus
  headline: string
  metrics: { label: string; value: string | number | null }[]
  note: string | null
}

/* ---------- 知识库 /api/kb ---------- */
export type ContentType = 'faq' | 'policy' | 'manual' | 'spec' | 'mined' | 'unmarked'
export type VectorStatus = 'pending' | 'done' | 'failed'

export interface KbChunkStats {
  total: number | null
  done: number | null
  pending: number | null
  key_clause: number | null
  by_content_type: Record<string, number>
}
export interface KbMilvus {
  online: boolean
  count: number | null
  collection?: string
  detail?: string
}
export interface StagingStats {
  counts: Record<StagingStatus, number>
  total: number
  batches: number
  latest_batch: string | null
}
export interface KbSource {
  file: string
  content_type: string
  present: boolean
  path: string
  chars?: number
  lines?: number
  mtime?: string
  chunks?: number
  key_clause?: number
  features?: SourceFeatures
}
export interface KbOverview {
  chunks: KbChunkStats
  milvus: KbMilvus
  consistent: boolean | null
  db_error: string | null
  staging: StagingStats | null
  sources: KbSource[]
  content_types: { key: string; desc: string }[]
  jobs: Job[]
}
export interface StoredChunk {
  id: number
  questions: string
  answer: string
  answer_chars: number
  category: string | null
  section_path: string | null
  content_type: ContentType | null
  is_key_clause: boolean
  status: VectorStatus
  created_at: string | null
  vector_id?: string | null
  review_id?: number | null
  prev_chunk_id?: number | null
  next_chunk_id?: number | null
}
export interface PreviewChunk {
  seq: number
  section_path: string
  category: string | null
  questions: string
  answer: string
  chars: number
  is_key_clause: boolean
  is_table: boolean
  duplicate: boolean | null
}
export interface PreviewResult {
  source: string
  content_type: string
  chars: number
  total: number
  duplicates: number
  key_clause: number
  features?: SourceFeatures
  chunks: PreviewChunk[]
  dedup_known: boolean
}
export interface SourceFeatures {
  sections: number
  table_split: boolean
  overlap: boolean
  multi_piece_sections?: string[]
}
export interface IngestResult {
  ids: number[]
  chunks: number
  inserted: number
  skipped: number
  skipped_samples: { questions: string; answer: string }[]
  vectorized: number | null
}
export type Strategy = 'vector' | 'bm25' | 'hybrid' | 'hybrid_rerank'
export interface SearchHit {
  id: number | null
  question: string | null
  answer: string | null
  score: number | null
  rerank_score: number | null
  section_path: string | null
  content_type: string | null
  category: string | null
}
export type StagingStatus = 'extracted' | 'kept' | 'discarded' | 'approved' | 'rejected'
export interface StagingRow {
  id: number
  batch_no: string
  source_ref: string | null
  question: string
  answer: string
}
export interface StagingList {
  stats: StagingStats
  rows: Record<StagingStatus, StagingRow[]>
  limit: number
}
export interface StagingDetail extends StagingRow {
  status: StagingStatus
  created_at: string | null
  material: {
    file: string | null
    status: 'available' | 'missing' | 'untrusted' | 'read_error'
    text: string | null
    valid: boolean | null
    reason: string | null
    sha256?: string | null
  }
}

/* ---------- 知识缺口审核 /api/review ---------- */
export type ReviewStatus = 'pending' | 'publishing' | 'approved' | 'rejected'
export interface ReviewItem {
  id: number
  question: string
  suggestion: string | null
  occurrence_count: number
  status: ReviewStatus
  review_status: string
  reviewer: string | null
  answer: string | null
  source_ref: string | null
  publish_error: string | null
  reviewed_at: string | null
  created_at: string | null
  source_digest?: string | null
  normalized_question?: string
  ai_suggested_answer?: string | null
  raws?: {
    raw_question: string
    source: string | null
    reason: string | null
    created_at: string | null
    retrieved_chunks?: { question?: string; section_path?: string; answer?: string; score?: number | null }[] | null
  }[]
}
export interface ProcessResult {
  created: number
  merged: number
  already: number
  skipped: number
  candidate_truncated: number
  skipped_reasons: Record<string, number>
}

/* ---------- RAG 质量 /api/rag-eval, /api/knowledge ---------- */
export interface StrategySummary {
  cases?: number
  answerable_cases?: number
  failures?: number
  recall_at_k?: number | null
  mrr?: number | null
  refusal_accuracy?: number | null
  keyword_coverage?: number | null
}
export type EvalHit = Partial<SearchHit> & { questions?: string; text?: string }
export interface EvalDetail {
  id: string
  strategy: string
  query: string
  should_refuse?: boolean | null
  error?: string | null
  recall?: number | null
  rr?: number | null
  coverage?: number | null
  refusal_correct?: boolean | null
  hits?: EvalHit[]
  answer?: string
  refused?: boolean
}
export interface EvalCase {
  id: string
  query: string
  should_refuse?: boolean | null
  groups?: string[][]
  expected_terms?: string[]
}
export interface RagReport {
  status: string
  message?: string
  k?: number | null
  generation?: boolean | null
  rewrite?: boolean | null
  split?: boolean | null
  summary?: Record<string, StrategySummary>
  details?: EvalDetail[]
  dataset?: EvalCase[]
  created_at?: string
}
export interface AnswerResult {
  answer: string
  refused: boolean
  reason: string | null
  citations: (EvalHit & { n: number })[]
}

/* ---------- 观测与成本 /api/observability ---------- */
interface Block {
  present: boolean
  status: 'ok' | 'missing' | 'error' | 'not_integrated'
  hint: string | null
}
export interface CostRow {
  intent: string
  requests?: number
  generations?: number
  input_tokens?: number
  output_tokens?: number
  unknown_usage?: number
  unpriced?: number
  priced_subtotals?: Record<string, string>
  price_versions?: string[]
  estimate_complete?: boolean
  duration_samples?: number
  p95_generation_ms?: number | null
}
export interface CostBlock extends Block {
  meta?: { generated_at?: string; source?: string; scope?: string; pricing_basis?: string }
  rows?: CostRow[]
  summary?: {
    requests?: number
    generations?: number
    known_input_tokens?: number
    known_output_tokens?: number
    unknown_usage?: number
    unpriced?: number
    usage_complete?: boolean
    estimate_complete?: boolean
  }
}
export interface EvalRun {
  id: number
  dataset_version?: string
  case_ids?: string[]
  config_version?: string
  kb_revision?: string
  strategy: string
  top_k: number
  triggered_by?: string
  status: string
  metrics: Record<string, number | null>
  details?: EvalDetail[]
  created_at?: string
  finished_at?: string
}
export interface TrendBlock extends Block {
  runs?: EvalRun[]
  metric_names?: string[]
  omitted_incomparable?: number
}
export type ScanRow = { threshold: number; pass_rate: number; leak_rate: number; youden_j: number }
export interface CalibrationBlock extends Block {
  scan?: ScanRow[]
  recommended?: ScanRow
  in_use?: number
  in_sync?: boolean
  created_at?: string
  dataset_version?: string
  scored?: { id: string; split?: string; answerable?: boolean | null; score: number }[]
  distribution?: Partial<Record<'answerable' | 'absent', { n?: number; min?: number; p25?: number; p50?: number; p75?: number; max?: number }>>
}
export interface ObservabilityOverview {
  cost: CostBlock
  trend: TrendBlock
  calibration: CalibrationBlock
}

/* ---------- 咨询主题 /api/topics ---------- */
export interface TopicDistribution {
  total: number
  latest: string | null
  source?: string
  classes: { label: string; count: number; samples: (string | { text?: string })[] }[]
}
export interface TopicQuestion {
  question_id: number | string
  labels: string[]
  text: string
  raw_question: string
  source: string
  occurrence_count: number
  review_status: string | null
  asked_at: string | null
}
export interface TopicCatalog {
  classes: { label: string; boundary: string }[]
}

/* ---------- 分类器 /api/acceptance ---------- */
export interface AcceptanceBlock {
  key: string
  no: number
  title: string
  status: 'pass' | 'fail' | 'missing'
  headline: string
  note: string
  jobs: string[]
}
export interface AcceptanceOverview {
  blocks: AcceptanceBlock[]
  passed: number
  total: number
  all_pass: boolean
  classifier: { online: boolean; detail: unknown }
  jobs: Job[]
}
export interface ClassMetric {
  name: string
  severity: string
  p: number
  r: number
  f1: number
  support: number
  red_line: number | null
  passed: boolean
  tp: number
  fp: number
  fn: number
  tn: number
}
export interface AcceptanceEval {
  eval: {
    present: boolean
    hint?: string
    ran_at?: string
    test_size?: number
    threshold?: number
    micro?: { p: number; r: number; f1: number }
    macro?: { p: number; r: number; f1: number }
    classes?: ClassMetric[]
    total_cells?: number
    total_fp?: number
    total_fn?: number
    red_line_passed?: boolean
  }
  scan: {
    present: boolean
    hint?: string
    scan?: { threshold: number; micro_f1: number; tp: number; fp: number; fn: number }[]
    best_threshold?: number
    in_use_threshold?: number
    consistent?: boolean
  }
  threshold_in_use: number | null
}
export interface FileStat {
  path: string
  present: boolean
  bytes?: number
  mtime?: string
  lines?: number
}
export interface AcceptanceData {
  lineage: (FileStat & { file: string; stage: string; desc: string; make: string })[]
  dataset: {
    splits: Record<string, { desc: string; size: number; multi_label: number; counts: Record<string, number> }>
    leaks: Record<string, number>
    clean: boolean
  }
  model: { files: FileStat[]; threshold: number | null; trio_ok: boolean }
  onnx: { files: FileStat[] }
  topic_names: string[]
}
export interface ClassifierError {
  text: string
  gold: string[]
  pred: string[]
  missed: string[]
  extra: string[]
  kind: '漏打' | '多打' | '错位' | string
  matrix_entries: number
}
export interface AcceptanceErrors {
  eval: { present: boolean; ran_at?: string; test_size?: number; threshold?: number; hint?: string }
  errors: ClassifierError[]
  kinds: Record<string, number>
  pairs: { missed: string; grabbed: string; count: number; severity: string | null }[]
  recipes?: Record<string, string>
}
export interface ClassifyResult {
  text: string
  threshold: number | null
  labels: string[]
  scores: { label: string; score: number; hit: boolean }[]
  fallback: boolean
}
