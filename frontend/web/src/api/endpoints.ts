// 所有后端接口集中在这里，页面只调用这些函数。
import { get, post } from './client'
import type {
  AcceptanceData,
  AcceptanceErrors,
  AcceptanceEval,
  AcceptanceOverview,
  AnswerResult,
  ClassifyResult,
  ContentType,
  EvalCase,
  IngestResult,
  Job,
  KbOverview,
  ModuleCard,
  ObservabilityOverview,
  Paged,
  PreviewResult,
  ProcessResult,
  RagReport,
  ReviewItem,
  SearchHit,
  StagingDetail,
  StagingList,
  StoredChunk,
  Strategy,
  TopicCatalog,
  TopicDistribution,
  TopicQuestion,
  VectorStatus,
} from './types'

const qs = (params: Record<string, string | number | undefined | null>) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/* 管理总览 */
export const getAdminOverview = () => get<{ modules: ModuleCard[] }>('/api/admin/overview')

/* 作业 */
export const listJobs = () => get<{ jobs: Job[] }>('/api/jobs')
export const getJob = (name: string) => get<Job>(`/api/jobs/${encodeURIComponent(name)}`)
export const startJob = (name: string) => post<Job>(`/api/jobs/${encodeURIComponent(name)}`)
export const stopJob = (name: string) => post<Job>(`/api/jobs/${encodeURIComponent(name)}/stop`)

/* 知识库 */
export const getKbOverview = () => get<KbOverview>('/api/kb/overview')
export const listChunks = (p: {
  page: number
  size: number
  q?: string
  status?: VectorStatus
  content_type?: ContentType
}) => get<Paged<StoredChunk>>(`/api/kb/chunks${qs(p)}`)
export const getChunk = (id: number) => get<StoredChunk>(`/api/kb/chunks/${id}`)
export const previewText = (text: string, content_type: string) =>
  post<PreviewResult>('/api/kb/preview', { text, content_type })
export const previewFile = (file: string) => post<PreviewResult>('/api/kb/preview', { file })
export const ingestText = (text: string, content_type: string, vectorize: boolean) =>
  post<IngestResult>('/api/kb/ingest', { text, content_type, vectorize }, 120000)
export const searchKb = (q: string, strategy: Strategy, top_k: number) =>
  post<{ hits: SearchHit[] }>('/api/kb/search', { q, strategy, top_k }, 30000)
export const listStaging = (limit = 30) => get<StagingList>(`/api/kb/staging${qs({ limit })}`)
export const getStaging = (id: number) => get<StagingDetail>(`/api/kb/staging/${id}`)
export const approveStaging = (ids: number[]) =>
  post<{ approved: number; chunk_ids: number[] }>('/api/kb/staging/approve', { ids }, 120000)
export const rejectStaging = (ids: number[]) =>
  post<{ rejected: number }>('/api/kb/staging/reject', { ids })

/* 知识缺口审核 */
export const listReviews = (p: { status?: string; page: number; size: number; q?: string }) =>
  get<Paged<ReviewItem>>(`/api/review/queue${qs(p)}`)
export const getReview = (id: number) => get<ReviewItem>(`/api/review/${id}`)
export const getMaterial = (file: string) =>
  get<{ file: string; text: string; sha256: string }>(`/api/review/materials/${encodeURIComponent(file)}`)
export const processReviews = (limit = 20) =>
  post<ProcessResult>(`/api/review/process${qs({ limit })}`, undefined, 180000)
export const approveReview = (id: number, approved_answer: string, source_ref: string) =>
  post<ReviewItem>(`/api/review/${id}/approve`, { approved_answer, source_ref }, 120000)
export const rejectReview = (id: number) => post<ReviewItem>(`/api/review/${id}/reject`)
export const retryPublish = (id: number) => post<ReviewItem>(`/api/review/${id}/publish`, undefined, 120000)

/* RAG 质量 */
export const getRagReport = () => get<RagReport>('/api/rag-eval/report')
export const getEvalState = () =>
  get<{ running: boolean; report_mtime: number | null }>('/api/knowledge/evaluation-state')
export const listEvalCases = () => get<{ cases: EvalCase[] }>('/api/knowledge/cases')
export const runEvaluation = (top_k: number, generate: boolean) =>
  post<RagReport>('/api/knowledge/evaluate', { top_k, generate }, 620000)
export const askKnowledge = (p: {
  query: string
  strategy: Strategy
  top_k: number
  rewrite: boolean
  split: boolean
}) => post<AnswerResult>('/api/knowledge/answer', p, 90000)

/* 观测与成本 */
export const getObservability = () => get<ObservabilityOverview>('/api/observability/overview')

/* 咨询主题 */
export const getTopicCatalog = () => get<TopicCatalog>('/api/topics/catalog')
export const getTopicDistribution = () => get<TopicDistribution>('/api/topics/distribution')
export const listTopicQuestions = (label: string, page: number, size: number) =>
  get<Paged<TopicQuestion> & { label: string }>(`/api/topics/questions${qs({ label, page, size })}`)

/* 分类器 */
export const getAcceptanceOverview = () => get<AcceptanceOverview>('/api/acceptance/overview')
export const getAcceptanceEval = () => get<AcceptanceEval>('/api/acceptance/eval')
export const getAcceptanceData = () => get<AcceptanceData>('/api/acceptance/data')
export const getAcceptanceErrors = () => get<AcceptanceErrors>('/api/acceptance/errors')
export const classifyText = (text: string) =>
  post<ClassifyResult>('/api/acceptance/classify', { text }, 30000)
