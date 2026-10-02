// 知识中心的页面状态。列表筛选条件写在 URL 上；录入草稿、预览和检索结果保存在模块内，
// 切换页面后再回来仍然保留（与 V2 一致）。
import { reactive } from 'vue'
import type { IngestResult, PreviewResult, SearchHit, Strategy } from '../../api/types'

export const typeNames: Record<string, string> = {
  faq: '商品问答',
  policy: '政策条款',
  manual: '售后手册',
  spec: '商品规格',
  mined: '对话提取',
}
export const typeName = (v?: string | null) => (v ? typeNames[v] || v : '未标注')

export const exampleText =
  '# 退换货政策\n\n## 申请条件\n签收后 7 天内可申请退货。商品需未使用，配件齐全。\n\n## 包装要求\n拆开外包装不直接等同于商品已使用，应由客服核对包装现状。'

export const kb = reactive({
  // 录入
  text: '',
  importType: 'policy',
  preview: null as PreviewResult | null,
  previewError: '',
  previewBusy: false,
  previewVersion: 0,
  fileVersion: 0,
  fileReading: false,
  fileName: '',
  fileNotice: '',
  ingestBusy: false,
  ingestResult: null as (IngestResult & { ids: number[] }) | null,
  ingestError: null as { uncertain: boolean; message: string } | null,
  // 检索自测
  searchQuery: '拆开外包装后还能退货吗？',
  strategy: 'hybrid' as Strategy,
  hits: null as SearchHit[] | null,
  searchError: '',
  searchBusy: false,
  // 向量补齐
  vectorChecking: false,
  vectorStarting: false,
  vectorNotice: '',
  vectorStartUnknown: false,
})

export function invalidatePreview() {
  if (kb.fileReading) kb.fileNotice = '文件读取已取消；当前正文已保留。'
  kb.fileVersion++
  kb.fileReading = false
  kb.previewVersion++
  kb.preview = null
  kb.previewBusy = false
  kb.previewError = ''
}

export const vectorLabels: Record<string, string> = {
  idle: '本次服务未运行',
  running: '运行中',
  ok: '进程执行完成',
  failed: '进程执行失败',
  stopped: '已停止',
}

export const stamp = (v?: string | null) => (v ? v.replace('T', ' ') : '—')
export const listStamp = (v?: string | null) => (v ? v.replace('T', ' ').slice(5, 16) : '—')
export const num = (v: unknown) => (v === null || v === undefined ? '—' : String(v))
