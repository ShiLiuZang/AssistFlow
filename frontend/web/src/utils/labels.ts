// 枚举值 → 中文显示名，以及对应的标签颜色
import type { JobState, ModuleStatus, ReviewStatus, StagingStatus, VectorStatus } from '../api/types'

export type Tone = 'green' | 'amber' | 'red' | 'neutral' | 'blue'

export const contentTypeNames: Record<string, string> = {
  faq: '商品问答',
  policy: '政策条款',
  manual: '售后手册',
  spec: '商品规格',
  mined: '对话挖掘',
  unmarked: '未标注',
}

export const vectorStatus: Record<VectorStatus, [string, Tone]> = {
  done: ['已向量化', 'green'],
  pending: ['待向量化', 'amber'],
  failed: ['向量化失败', 'red'],
}

export const jobStatus: Record<JobState, [string, Tone]> = {
  idle: ['未运行', 'neutral'],
  running: ['运行中', 'blue'],
  ok: ['成功', 'green'],
  failed: ['失败', 'red'],
  stopped: ['已停止', 'amber'],
}

export const moduleStatus: Record<ModuleStatus, [string, Tone]> = {
  ok: ['正常', 'green'],
  attention: ['需关注', 'amber'],
  missing: ['尚无数据', 'neutral'],
  error: ['读取失败', 'red'],
}

export const reviewStatus: Record<ReviewStatus, [string, Tone]> = {
  pending: ['待审', 'amber'],
  publishing: ['发布中', 'blue'],
  approved: ['已通过', 'green'],
  rejected: ['已驳回', 'neutral'],
}

export const stagingStatus: Record<StagingStatus, [string, Tone]> = {
  extracted: ['已抽取', 'neutral'],
  kept: ['待审', 'amber'],
  discarded: ['已丢弃', 'neutral'],
  approved: ['已入库', 'green'],
  rejected: ['已驳回', 'neutral'],
}

export const strategyNames: Record<string, string> = {
  vector: '纯向量',
  bm25: 'BM25',
  hybrid: '混合检索',
  hybrid_rerank: '混合 + 重排',
}

export const acceptanceStatus: Record<'pass' | 'fail' | 'missing', [string, Tone]> = {
  pass: ['达标', 'green'],
  fail: ['未达标', 'red'],
  missing: ['未生成', 'neutral'],
}

export const refusalReasons: Record<string, string> = {
  no_evidence: '检索无结果',
  grounding_failed: '答案未通过溯源校验',
  unsupported_answer: '模型判断证据不足',
}
