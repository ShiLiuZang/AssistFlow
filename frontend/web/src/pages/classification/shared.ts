// 咨询主题与分类器共用的格式化与文案（对应 V2 admin-classification.js）
import { reactive } from 'vue'
import type { FileStat } from '../../api/types'

export const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
export const dec = (v: unknown) => (finite(v) ? v.toFixed(4) : '—')
export const pct = (v: unknown) => (finite(v) ? (100 * v).toFixed(1) + '%' : '—')
export const num = (v: unknown) => (v == null ? '—' : String(v))
export const formatted = (v: unknown) => (finite(v) ? v.toLocaleString('zh-CN') : '—')
export const stamp = (v?: string | null) => (v ? v.replace('T', ' ') : '—')

const sourceNames: Record<string, string> = {
  conversation_history: '历史会话隔离归类',
  low_confidence_pool: '低置信问题池',
  retrieval_low_conf: '低置信检索',
  self_check: '回答自检',
  user_feedback: '用户反馈',
  simulated: 'LLM 补造',
  augmented: '训练增强',
  supplement: '定向补数',
  unmarked: '未标注',
}
export const source = (v?: string | null) => (v && sourceNames[v]) || v || '未标注'
export const origin = (v?: string | null) => (v === 'conversation_history' ? '历史真实提问' : source(v))
export const reviewNames: Record<string, string> = { pending: '待审', approved: '已通过', rejected: '已驳回', publishing: '发布中' }

export function serviceDetail(v: unknown) {
  if (v && typeof v === 'object') return (v as { ok?: unknown }).ok === true ? '健康检查通过' : JSON.stringify(v)
  const text = String(v || '')
  if (text.startsWith('ConnectTimeout:')) return '连接分类服务超时，请确认推理服务正在运行。'
  if (text.startsWith('ConnectError:')) return '无法连接分类服务，请检查服务状态。'
  return text || '未提供'
}
// 报告未生成 / 解析失败时的提示文案；已生成返回 null
export const missingText = (r?: { present?: boolean; hint?: string } | null) =>
  r?.present === true ? null : r?.hint?.startsWith('产物解析失败') ? '报告读取失败，请检查保存文件后刷新。' : '报告尚未生成；当前页面只读取已有结果。'

export const jobTitles: Record<string, string> = {
  'finetune-corpus': '构建主题语料',
  'finetune-dataset': '划分与增强数据集',
  'finetune-golden': '黄金样例校验',
  'finetune-train': '训练分类器',
  'finetune-export': '导出 ONNX',
  'classifier-up': '启动分类服务',
  'finetune-eval': '测试集评测',
  'finetune-threshold-scan': '重演阈值扫描',
  'classify-history': '归类历史提问',
  'classify-pool': '批量归类问题池',
  'classify-pool-force': '强制归类小批次',
}

export const filename = (path?: string) => (path ? String(path).split(/[\\/]/).pop() : '未标注文件')
export const fileContext = (f: FileStat) =>
  f.stage ||
  ({ model: '训练模型', onnx: '推理文件' } as Record<string, string>)[String(f.path || '').split(/[\\/]/).slice(-2, -1)[0]?.trim() ?? ''] ||
  (filename(f.path) === 'sample_review.md' ? '语料复核' : '用途未标注')
export const bytes = (v: unknown) => (finite(v) ? (v >= 1048576 ? (v / 1048576).toFixed(1) + ' MB' : v >= 1024 ? (v / 1024).toFixed(1) + ' KB' : v + ' B') : '—')
export const splitNames: Record<string, string> = { train: '训练集', val: '验证集', test: '测试集' }

// 页面内状态：错例筛选与单句试分类（切换子页后保留）
export const local = reactive({ kind: 'all', errorQuery: '', trialText: '', trialResult: null as null | import('../../api/types').ClassifyResult, trialError: '', trialEdited: false })
