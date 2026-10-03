// 人工坐席工作台接口（/api/agent/*，员工令牌，坐席或管理员）。
import { get, post } from './client'

export type HandoffStatus = 'queued' | 'active' | 'closed' | 'cancelled'
export type ConvStatus = 'queued' | 'active' | 'ai' | 'closed' | 'cancelled'
export type ListView = 'queued' | 'mine' | 'active' | 'ai' | 'closed'

export interface HandoffCard {
  reason: string
  reason_label: string
  summary: string
  last_question: string
  recent: { role: 'customer' | 'bot'; content: string }[]
  intent: string | null
  evidence: { title: string; text: string }[]
  order: Record<string, string | number> | null
  mood: { level: 'calm' | 'upset' | 'angry'; label: string; hits: string[]; method: string }
}

export interface Handoff {
  id: number
  conversation_id: number
  status: HandoffStatus
  reason: string
  reason_label: string
  position: number | null
  created_at: string | null
  accepted_at: string | null
  closed_at: string | null
  user_id: string
  assignee: string | null
  card: HandoffCard | null
  closed_by: string | null
}

export interface AgentMessage {
  id: number
  role: 'customer' | 'bot' | 'staff' | 'note' | 'system'
  content: string
  created_at: string | null
  author?: string
}

export type Channel = 'web' | 'pinduoduo'

export const channelText: Record<Channel, string> = { web: '网页', pinduoduo: '拼多多' }

export interface ConversationItem {
  conversation_id: number
  user_id: string
  channel: Channel
  status: ConvStatus
  handoff: Handoff | null
  last_message: AgentMessage | null
}

export interface Ticket {
  ticket_no: string
  conversation_id: number
  user_id: string | null
  ticket_type: string
  title: string
  description: string
  status: TicketStatus
  priority: '普通' | '优先'
  assignee: string | null
  source: 'customer' | 'staff'
  created_at: string | null
  updated_at: string | null
  events?: { actor: string; action: string; from_status: string | null; to_status: string | null; note: string | null; created_at: string | null }[]
}

export type TicketStatus = '待处理' | '处理中' | '已解决' | '已关闭'
export const TICKET_STATUSES: TicketStatus[] = ['待处理', '处理中', '已解决', '已关闭']
export const TICKET_TYPES = ['退款', '退货', '换货', '补发', '物流', '投诉', '咨询', '其他']
export const TICKET_NEXT: Record<TicketStatus, TicketStatus[]> = {
  待处理: ['处理中', '已关闭'],
  处理中: ['已解决', '待处理', '已关闭'],
  已解决: ['处理中', '已关闭'],
  已关闭: [],
}

export interface ConversationDetail {
  conversation_id: number
  user_id: string
  channel: Channel
  status: ConvStatus
  handoff: Handoff | null
  messages: AgentMessage[]
  tickets: Ticket[]
}

export interface AgentSummary {
  queued: number
  mine: number
  active: number
  tickets: Record<TicketStatus, number>
}

const enc = encodeURIComponent

export const agentSummary = () => get<AgentSummary>('/api/agent/summary')
export const listConversations = (view: ListView) => get<ConversationItem[]>(`/api/agent/conversations?view=${view}`)
export const conversationDetail = (id: number) => get<ConversationDetail>(`/api/agent/conversations/${id}`)
export const acceptConversation = (id: number) => post<Handoff>(`/api/agent/conversations/${id}/accept`)
export const postMessage = (id: number, text: string, kind: 'reply' | 'note') =>
  post<AgentMessage>(`/api/agent/conversations/${id}/messages`, { text, kind })
export const transferConversation = (id: number, to: string) => post<Handoff>(`/api/agent/conversations/${id}/transfer`, { to })
export const closeConversation = (id: number) => post<Handoff & { harvested: number }>(`/api/agent/conversations/${id}/close`)
export const listStaff = () => get<{ username: string; role: string }[]>('/api/agent/staff')

export const listTickets = (status?: TicketStatus | '', q = '') =>
  get<Ticket[]>(`/api/agent/tickets?${status ? `status=${enc(status)}&` : ''}q=${enc(q)}`)
export const ticketDetail = (no: string) => get<Ticket>(`/api/agent/tickets/${enc(no)}`)
export const createTicket = (body: { conversation_id: number; ticket_type: string; title: string; description: string; priority: string }) =>
  post<Ticket>('/api/agent/tickets', body)
export const changeTicket = (no: string, status: TicketStatus, note = '') =>
  post<Ticket>(`/api/agent/tickets/${enc(no)}/status`, { status, note })

/** 后端时间为不带时区的 UTC（与客户咨询页一致），显示为本地时间：15:04（今天）或 10-01 15:04 */
export function shortTime(raw: string | null | undefined) {
  if (!raw) return ''
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(raw) ? raw : raw.replace(' ', 'T') + 'Z')
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  return d.toDateString() === new Date().toDateString() ? time : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${time}`
}

export const statusText: Record<ConvStatus, string> = {
  queued: '排队中',
  active: '人工接待',
  ai: 'AI 接待',
  closed: '已结束',
  cancelled: '已取消',
}
export const statusColor = (s: ConvStatus) => (s === 'queued' ? 'amber' : s === 'active' ? 'blue' : s === 'ai' ? '' : 'neutral')
export const ticketColor = (s: TicketStatus) => (s === '待处理' ? 'amber' : s === '处理中' ? 'blue' : s === '已解决' ? '' : 'neutral')
