// RAG 质量与观测成本共用的格式化、筛选状态与单题体验状态（对应 V2 admin-reports.js）
import { reactive } from 'vue'
import type { EvalDetail, RagReport } from '../../api/types'

export const strategyNames: Record<string, string> = { vector: '纯向量', bm25: 'BM25', hybrid: '混合检索', hybrid_rerank: '混合 + 重排' }
export const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
export const decimal = (v: unknown, missing = '—') => (finite(v) ? v.toFixed(3) : missing)
export const percent = (v: unknown, missing = '—') => (finite(v) ? (v * 100).toFixed(1) + '%' : missing)
export const name = (v?: string | null) => (v && strategyNames[v]) || v || '未标注'
export const count = (v: unknown) => (finite(v) ? v.toLocaleString('zh-CN') : '—')
export const judge = (v?: boolean | null) => (v === true ? '应拒答' : v === false ? '可回答' : '未标注')
export const listStamp = (v?: string | null) => (v ? v.replace('T', ' ').slice(5, 16) : '—')

// 带时区的时间统一换算到 UTC+8 展示；不带时区的原样展示
export function reportTime(value?: string | null, missing = '生成时间未标注') {
  if (typeof value !== 'string') return missing
  if (!/(Z|[+-]\d{2}:\d{2})$/.test(value)) return value.replace('T', ' ').slice(0, 19)
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Singapore', dateStyle: 'short', timeStyle: 'medium', hour12: false }).format(date) + ' (UTC+8)'
}

export type Outcome = [key: string, label: string, color: string]
export function outcome(row: EvalDetail, report: RagReport): Outcome {
  if (row.error) return ['error', '调用失败', 'red']
  if (report.generation === false) return ['retrieval', '仅检索', 'neutral']
  if (row.refusal_correct === true) return ['correct', '拒答判断符合', '']
  if (row.refusal_correct === false) return ['incorrect', '拒答判断不符', 'amber']
  return ['unknown', '生成未评估', 'neutral']
}

// 页面内的展示选择（不进 URL：只是看哪个指标）
export const reportUI = reactive({ metric: 'mrr', generationStrategy: 'hybrid_rerank', query: '', trendMetric: 'mrr' })

// 单题体验：切换子页后保留问题与结果
export const trial = reactive({
  query: '',
  strategy: 'vector',
  topK: 5 as number | string,
  rewrite: false,
  split: false,
  busy: false,
  result: null as null | { answer: string; refused: boolean; citations: { n: number; section_path?: string | null; question?: string | null; answer?: string | null }[] },
  time: null as string | null,
  error: '',
  version: 0,
})
export function invalidateTrial() {
  trial.version++
  trial.result = null
  trial.time = null
  trial.error = ''
}

export const guideHtml =
  '<p>页面展示后端已保存的报告；RAG 质量页可核对题集、检索数量和是否生成回答，再确认运行评估。浏览页面不会自动启动评估。</p><p class="field-hint section-gap">观测报告生成与阈值改写没有对应操作接口，本页保持查询。没有报告时保留空状态，读取失败时保留未知读数；进程完成不代替报告中的质量结论。</p>'
