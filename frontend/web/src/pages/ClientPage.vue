<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { get, post, request } from '../api/client'
import { AUTH_EXPIRED_EVENT, authFetch, session, setCustomer } from '../auth/session'
import { readChatStream } from '../api/chatStream'
import Icon from '../components/Icon.vue'

type Message = { role: string; content: string; message_id?: string | null; citations?: Record<string, any>[]; feedback?: string }
type Pending = { kind: string; tool_call_id?: string; request_id?: string; preview?: Record<string, unknown>; orders?: { order_id: string; product?: string; status?: string; amount?: number }[]; confirmed?: boolean | null }
const catUrl = `${import.meta.env.BASE_URL}assets/minihelp-cat.svg`
const client = useQueryClient()
const route = useRoute()
const router = useRouter()
// 顾客身份来自令牌：嵌入方通过 URL 参数 token 或 postMessage 传入；开发模式下可以模拟
const user = computed(() => session.customer?.userId ?? '')
const devMode = ref(false)
const identity = ref('')
const conversations = ref<{ id: number; created_at: string }[]>([])
const conversationId = ref<number | null>(null)
const messages = ref<Message[]>([])
const pending = ref<Pending | null>(null)
const draft = ref(''), error = ref(''), historyError = ref('')
const busy = ref(false), loading = ref(false), uncertain = ref(false), feedbackBusy = ref(false)
const historyOpen = ref(false)
const list = ref<HTMLElement | null>(null)
let controller: AbortController | undefined
let disposed = false
const locked = computed(() => busy.value || loading.value || feedbackBusy.value)
const canSend = computed(() => !!user.value && !locked.value && !uncertain.value && !pending.value && !!draft.value.trim())
const key = () => `minihelp-web-conversation:${user.value}`
function tokenSubject(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof payload.sub === 'string' && payload.sub ? payload.sub : null
  } catch {
    return null
  }
}
function acceptToken(token: unknown) {
  if (typeof token !== 'string') return false
  const userId = tokenSubject(token)
  if (!userId) return false
  setCustomer({ token, userId })
  return true
}
function historyTime(raw: string) {
  const parsed = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(raw) ? raw : raw.replace(' ', 'T') + 'Z')
  return Number.isNaN(parsed.getTime()) ? '时间未知' : new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(parsed)
}
const scroll = () => nextTick(() => { if (list.value) list.value.scrollTop = list.value.scrollHeight })
const remember = (id: number | null) => {
  conversationId.value = id
  if (id) localStorage.setItem(key(), String(id))
  else localStorage.removeItem(key())
}
async function history() {
  try {
    if (!user.value) { conversations.value = []; return }
    conversations.value = await request('/api/conversations')
    historyError.value = ''
  } catch (e) { historyError.value = (e as Error).message }
}
async function restore(id: number) {
  if (locked.value) return
  loading.value = true
  error.value = ''
  try {
    const [rows, action] = await Promise.all([
      request<Message[]>(`/api/conversations/${id}/messages`),
      request<Pending | null>(`/api/actions/pending?conversation_id=${id}`),
    ])
    remember(id)
    messages.value = rows.filter(r => ['user', 'assistant'].includes(r.role) && r.content)
    pending.value = action
    uncertain.value = false
    await scroll()
  } catch (e) { error.value = (e as Error).message; uncertain.value = true }
  finally { loading.value = false }
}
function fresh() {
  if (locked.value) return
  remember(null)
  messages.value = []
  pending.value = null
  draft.value = error.value = ''
  uncertain.value = false
}
async function load() {
  conversationId.value = null
  messages.value = []; pending.value = null; uncertain.value = false; error.value = ''; draft.value = ''
  loading.value = true
  await history()
  loading.value = false
  const id = Number(localStorage.getItem(key()))
  if (user.value && Number.isSafeInteger(id) && id > 0) await restore(id)
}
// 开发模式：模拟电商主站为指定顾客签发令牌
async function changeIdentity() {
  if (locked.value || !identity.value.trim()) return
  try {
    const result = await post<{ access_token: string }>('/api/auth/dev/customer-token', { user_id: identity.value.trim() })
    if (!acceptToken(result.access_token)) throw new Error('令牌格式不正确')
    await load()
  } catch (e) { error.value = (e as Error).message }
}
async function run(path: string, extra: Record<string, unknown>) {
  if (locked.value) return
  busy.value = true; error.value = ''
  const reply = ref<Message>({ role: 'assistant', content: '', citations: [] })
  messages.value.push(reply.value)
  controller = new AbortController()
  const timer = setTimeout(() => controller?.abort(), 120000)
  let completed = false
  try {
    const response = await authFetch(path, { method: 'POST', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ conversation_id: conversationId.value, ...extra }) })
    await readChatStream(response, event => {
      if (event.conversation_id) remember(event.conversation_id)
      if (typeof event.delta === 'string') reply.value.content += event.delta
      if (event.event === 'citations') reply.value.citations = event.items || []
      if (event.event === 'done') { reply.value.message_id = event.message_id; pending.value = null; completed = true }
      if (event.event === 'interrupt') {
        pending.value = event as Pending
        reply.value.content ||= '请核对下方信息，再选择继续或取消。'
        completed = true
      }
      scroll()
    })
    if (!completed) throw new Error('没有收到完成结果，请重新读取会话')
    if (!reply.value.content) reply.value.content = '本次未返回回复正文。'
    client.invalidateQueries({ queryKey: ['review'] })
  } catch (e) {
    uncertain.value = true
    error.value = (e as Error).name === 'AbortError' ? '已停止接收回复，后台可能仍在处理。请重新读取会话后继续。' : (e as Error).message
    if (!reply.value.content) messages.value.pop()
  } finally {
    clearTimeout(timer); busy.value = false; controller = undefined
    if (!disposed) { await history(); await scroll() }
  }
}
async function send(text = draft.value) {
  if (locked.value || pending.value || uncertain.value || !text.trim()) return
  draft.value = ''
  messages.value.push({ role: 'user', content: text.trim() })
  await run('/api/graph-chat', { message: text.trim() })
}
async function decide(confirmed: boolean) {
  if (!pending.value?.tool_call_id) return
  if (pending.value.confirmed != null && pending.value.confirmed !== confirmed) return
  await run('/api/actions/resume', { tool_call_id: pending.value.tool_call_id, confirmed })
}
async function choose(orderId?: string) {
  if (!pending.value?.request_id) return
  await run('/api/actions/select-order', { kind: 'select_order', request_id: pending.value.request_id,
    ...(orderId ? { order_id: orderId, cancelled: false } : { cancelled: true }) })
}
async function feedback(message: Message, rating: 'up' | 'down') {
  if (!message.message_id || locked.value || message.feedback) return
  feedbackBusy.value = true
  try {
    const result = await request<{ pool_id: number | null }>('/api/feedback', { method: 'POST', body: {
      conversation_id: conversationId.value, message_id: message.message_id, rating,
    } })
    message.feedback = result.pool_id ? '已记录未解决问题，等待后台归并' : '感谢反馈'
    client.invalidateQueries({ queryKey: ['review'] })
  } catch (e) { error.value = (e as Error).message }
  finally { feedbackBusy.value = false }
}
const ticketNames: Record<string, string> = { order_id: '订单号', reason: '原因', description: '描述', ticket_type: '工单类型', type: '类型', user_id: '用户' }
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (canSend.value) send() }
}
function onMessage(e: MessageEvent) {
  // 嵌入在商城页面中时，由父页面传入顾客令牌；令牌由后端校验，这里只取出顾客 ID 用于展示
  if (e.source === window.parent && e.data?.type === 'assistflow:customer-token' && acceptToken(e.data.token)) load()
}
function onExpired(e: Event) {
  if ((e as CustomEvent<{ kind: string }>).detail?.kind === 'customer') {
    error.value = '登录已失效，请从商城重新进入咨询。'
    conversations.value = []
  }
}
onMounted(async () => {
  window.addEventListener('message', onMessage)
  window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
  if (acceptToken(route.query.token)) {
    // 令牌不留在地址栏里，避免被复制或记录
    const { token: _token, ...rest } = route.query
    await router.replace({ query: rest })
  }
  try { devMode.value = (await get<{ dev_mode: boolean }>('/api/auth/config')).dev_mode } catch { devMode.value = false }
  await load()
})
onBeforeUnmount(() => {
  disposed = true; controller?.abort()
  window.removeEventListener('message', onMessage)
  window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
})
</script>

<template>
  <main class="live-client">
    <header class="live-store-header"><div class="store-brand"><img :src="catUrl" alt="" />喵喵优选 <small>在线咨询</small></div><RouterLink to="/overview" class="text-button">管理后台 →</RouterLink></header>
    <div class="live-chat-layout">
      <aside class="live-chat-sidebar" :class="{ expanded: historyOpen }">
        <h1>有问题，聊一聊。</h1><p class="muted">商品、订单与售后，随时咨询。</p>
        <button class="btn primary" :disabled="locked" @click="fresh">＋ 新建会话</button>
        <button class="btn soft live-mobile-history-toggle" :aria-expanded="historyOpen" @click="historyOpen = !historyOpen">{{ historyOpen ? '收起' : '历史会话与用户' }}</button>
        <details v-if="devMode" class="live-identity" :open="!user"><summary>{{ user ? `模拟顾客：${user}` : '开发模式：选择模拟顾客' }}</summary><form @submit.prevent="changeIdentity"><label>顾客 ID<input v-model="identity" aria-label="模拟顾客 ID" maxlength="64" :disabled="locked" /></label><button class="btn" :disabled="locked || !identity.trim()">进入</button></form><small>仅开发模式可用，模拟电商主站签发顾客令牌。</small></details>
        <p v-else-if="user" class="muted small">当前顾客：{{ user }}</p>
        <div class="between"><h2>历史会话</h2><button class="text-button" :disabled="locked" @click="history">刷新</button></div>
        <p v-if="historyError" class="notice amber" role="alert">{{ historyError }}</p>
        <nav class="live-history" aria-label="历史会话"><button v-for="c in conversations" :key="c.id" :class="{ active: conversationId === c.id }" :disabled="locked" @click="restore(c.id)"><strong>会话 #{{ c.id }}</strong><small>{{ historyTime(c.created_at) }} · UTC+8</small></button><p v-if="!conversations.length && !historyError" class="muted">发送第一条消息后，会话会保存在这里。</p></nav>
      </aside>
      <section class="live-chat-window" aria-label="客户咨询窗口">
        <header class="live-chat-heading"><span class="avatar green"><Icon name="spark" /></span><div><h2>Minihelp 助手</h2><p>{{ busy ? '正在处理您的问题…' : loading ? '正在读取会话…' : pending ? '等待您确认' : conversationId ? `会话 #${conversationId}` : '开始新的咨询' }}</p></div><button v-if="conversationId" class="btn soft" :disabled="locked" @click="restore(conversationId)">重新读取会话</button></header>
        <div ref="list" class="live-messages" aria-label="会话消息" :aria-busy="busy || loading">
          <div v-if="!user" class="live-chat-empty"><img :src="catUrl" alt="" /><h2>请先登录商城</h2><p>{{ devMode ? '开发模式：在左侧输入顾客 ID 模拟登录。' : '请从商城页面的「联系客服」入口进入咨询。' }}</p></div>
          <div v-else-if="!messages.length" class="live-chat-empty"><img :src="catUrl" alt="" /><h2>你好，有什么可以帮你？</h2><p>你可以描述遇到的问题，或从下面开始。</p><div><button class="btn soft" :disabled="locked" @click="send('无理由退货有什么条件？')">退换货条件</button><button class="btn soft" :disabled="locked" @click="send('帮我查一下我的订单')">查询订单</button></div></div>
          <article v-for="(m, i) in messages" :key="i" class="live-message" :class="m.role">
            <span class="live-speaker">{{ m.role === 'user' ? '我' : 'Minihelp' }}</span><div class="live-bubble">{{ m.content || '正在核对信息，请稍候…' }}</div>
            <details v-if="m.citations?.length" class="live-citations"><summary>回复依据 · {{ m.citations.length }} 条</summary><div v-for="(c, n) in m.citations" :key="n"><strong>{{ c.section_path || c.title || c.source || `依据 ${n + 1}` }}</strong><p>{{ c.answer || c.text || c.content || c.quote || '' }}</p></div></details>
            <div v-if="m.role === 'assistant' && m.message_id" class="live-feedback"><span v-if="m.feedback" role="status">{{ m.feedback }}</span><template v-else><button :disabled="locked" @click="feedback(m, 'up')">有帮助</button><button :disabled="locked" @click="feedback(m, 'down')">未解决</button></template></div>
          </article>
          <section v-if="pending" class="live-pending" aria-label="待确认操作">
            <template v-if="pending.kind === 'confirm_ticket'"><h3>请核对工单信息</h3><dl><template v-for="(v, k) in pending.preview" :key="k"><dt>{{ ticketNames[String(k)] || k }}</dt><dd>{{ v }}</dd></template></dl><template v-if="pending.confirmed != null"><p>上次{{ pending.confirmed ? '确认' : '取消' }}已记录，可继续恢复该操作。</p><button class="btn primary" :disabled="locked || uncertain" @click="decide(pending.confirmed)">恢复上次操作</button></template><template v-else><p>确认后将提交工单。</p><button class="btn primary" :disabled="locked || uncertain" @click="decide(true)">确认提交</button><button class="btn" :disabled="locked || uncertain" @click="decide(false)">取消</button></template></template>
            <template v-else-if="pending.kind === 'select_order'"><h3>请选择要处理的订单</h3><button v-for="o in pending.orders" :key="o.order_id" class="live-order" :disabled="locked || uncertain" @click="choose(o.order_id)"><strong>{{ o.order_id }}</strong><span>{{ o.product }} · {{ o.status }}<template v-if="o.amount != null"> · ¥{{ o.amount }}</template></span></button><button class="btn" :disabled="locked || uncertain" @click="choose()">取消选择</button></template>
            <p v-else>存在待处理操作，请重新读取会话核对。</p>
          </section>
        </div>
        <div v-if="error" class="live-chat-error" role="alert">{{ error }}<button v-if="conversationId" class="text-button" :disabled="locked" @click="restore(conversationId)">重新读取</button><button v-else class="text-button" :disabled="locked" @click="fresh">新建会话</button></div>
        <form class="live-composer" @submit.prevent="send()"><textarea id="client-draft" v-model="draft" aria-label="咨询内容" :disabled="!user || loading || !!pending || uncertain" placeholder="说说你遇到的问题…" maxlength="2000" @keydown="onKey"></textarea><div><small>{{ pending ? '请先处理上方待确认操作' : 'Enter 发送 · Shift + Enter 换行' }}</small><button v-if="busy" class="btn" type="button" @click="controller?.abort()">停止接收</button><button v-else class="btn primary" :disabled="!canSend">发送 <Icon name="send" /></button></div></form>
      </section>
    </div>
  </main>
</template>
