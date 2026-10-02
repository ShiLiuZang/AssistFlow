// 坐席工作台的实时连接：登录员工进入客服工作台后建立一条 /api/agent/stream，
// 收到事件就让相关查询失效重拉（列表、会话详情、工单、计数），页面本身不用关心推送细节。
import { reactive } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import { subscribe, type LiveEvent, type Subscription } from '../api/events'
import { toast } from './useToast'

export const agentLive = reactive({ connected: false })

let subscription: Subscription | null = null

function onEvent(client: QueryClient, event: LiveEvent) {
  const id = event.conversation_id
  if (event.type === 'handoff') {
    client.invalidateQueries({ queryKey: ['agent', 'conversations'] })
    client.invalidateQueries({ queryKey: ['agent', 'summary'] })
    if (id) client.invalidateQueries({ queryKey: ['agent', 'conversation', id] })
    const h = event.handoff
    if (h?.status === 'queued' && h?.position && !h?.accepted_at) toast(`新的转人工会话 #${id}：${h.reason_label}`)
  } else if (event.type === 'message') {
    if (id) client.invalidateQueries({ queryKey: ['agent', 'conversation', id] })
    client.invalidateQueries({ queryKey: ['agent', 'conversations'] })
  } else if (event.type === 'ticket') {
    client.invalidateQueries({ queryKey: ['agent', 'tickets'] })
    client.invalidateQueries({ queryKey: ['agent', 'summary'] })
    if (id) client.invalidateQueries({ queryKey: ['agent', 'conversation', id] })
  }
}

export function startAgentLive(client: QueryClient) {
  if (subscription) return
  subscription = subscribe('/api/agent/stream', {
    onEvent: (event) => onEvent(client, event),
    // 连上（含重连）后统一重拉一次，补上断线期间错过的变化
    onOpen: () => client.invalidateQueries({ queryKey: ['agent'] }),
    onState: (connected) => (agentLive.connected = connected),
  })
}

export function stopAgentLive() {
  subscription?.close()
  subscription = null
  agentLive.connected = false
}
