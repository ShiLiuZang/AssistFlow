// 知识缺口与作业中心共用的标签和草稿（对应 V2 admin-workflows.js）
import { reactive } from 'vue'

export const reviewLabels: Record<string, string> = { pending: '待审', publishing: '发布中', approved: '已通过', rejected: '已驳回' }
export const reviewApiStatus: Record<string, string> = { pending: '待审', publishing: '发布中', approved: '通过', rejected: '驳回' }
export const reviewColor = (s: string) => (s === 'pending' || s === 'publishing' ? 'amber' : s === 'rejected' ? 'neutral' : '')

export const jobLabels: Record<string, string> = { idle: '本次未运行', running: '运行中', ok: '进程执行完成', failed: '进程执行失败', stopped: '已停止' }
export const jobColor = (s: string) => (s === 'failed' ? 'red' : s === 'running' ? 'blue' : s === 'idle' || s === 'stopped' ? 'neutral' : '')
export const jobGroup = (name: string) => (name.startsWith('kb-') ? '知识处理' : name.startsWith('classif') ? '归类与服务' : '训练与评测')
export const jobResultPage = (name: string) => (name === 'kb-mine' ? '/knowledge?tab=mining' : ['kb-preview', 'kb-build'].includes(name) ? '/knowledge?tab=import' : name.startsWith('kb-') ? '/knowledge?tab=index' : name.startsWith('classify') ? '/topics' : '/models')

export const sourceLabels: Record<string, string> = { retrieval_low_conf: '检索置信度低', self_check: '模型自评不足', user_feedback: '用户反馈未解决' }
export const materialNames = ['returns-policy.md', 'product-faq.md', 'after-sales-manual.md', 'product-specs.md', 'member-benefits.md', 'billing-shipping.md']

// 审核草稿：重新打开同一条记录时保留填写内容
export const reviewDraft = reactive({ id: null as number | null, answer: '', source: '' })

export const stamp = (v?: string | null) => (v ? v.replace('T', ' ') : '—')
export const listStamp = (v?: string | null) => (v ? v.replace('T', ' ').slice(5, 16) : '—')
