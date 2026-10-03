<!-- 会话工作台：排队接入、人工回复、内部备注、转交、结束接待、建工单（真实接口，实时推送） -->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import { openModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { useUrlState } from '../../composables/useUrlState'
import { hasRole, session } from '../../auth/session'
import Avatar from '../../demo/Avatar.vue'
import FinishModal from '../demo/FinishModal.vue'
import AgentMessages from './AgentMessages.vue'
import NewTicketModal from './NewTicketModal.vue'
import TransferModal from './TransferModal.vue'
import {
  acceptConversation, agentSummary, channelText, closeConversation, conversationDetail, listConversations, postMessage,
  shortTime, statusColor, statusText, ticketColor, transferConversation, type ListView,
} from '../../api/agent'

const client = useQueryClient()
const me = computed(() => session.staff?.username ?? '')
const isAdmin = computed(() => session.staff?.role === 'admin')
const allowed = computed(() => hasRole('agent'))

const viewParam = useUrlState('view', 'queued')
const view = computed({ get: () => viewParam.value as ListView, set: (v: ListView) => (viewParam.value = v) })
const selectedRaw = useUrlState('c', '')
const selected = computed(() => Number(selectedRaw.value) || 0)
const search = ref('')
const mode = ref<'reply' | 'note'>('reply')
const drafts = ref<Record<string, string>>({})
const busy = ref(false)

const summary = useQuery({ queryKey: ['agent', 'summary'], queryFn: agentSummary, enabled: allowed })
const list = useQuery({
  queryKey: computed(() => ['agent', 'conversations', view.value]),
  queryFn: () => listConversations(view.value),
  enabled: allowed,
})
const detail = useQuery({
  queryKey: computed(() => ['agent', 'conversation', selected.value]),
  queryFn: () => conversationDetail(selected.value),
  enabled: computed(() => allowed.value && selected.value > 0),
})

const tabs = computed<[ListView, string, number | string][]>(() => [
  ['queued', '待接待', summary.data.value?.queued ?? ''],
  ['mine', '我的', summary.data.value?.mine ?? ''],
  ['active', '进行中', summary.data.value?.active ?? ''],
  ['ai', 'AI 接待', ''],
  ['closed', '已结束', ''],
])
const filtered = computed(() =>
  (list.data.value ?? []).filter((x) => `${x.user_id}#${x.conversation_id}${channelText[x.channel] ?? ''}${x.last_message?.content ?? ''}`.toLowerCase().includes(search.value.trim().toLowerCase())),
)

const d = computed(() => detail.data.value)
const handoff = computed(() => d.value?.handoff ?? null)
const card = computed(() => handoff.value?.card ?? null)
const status = computed(() => d.value?.status ?? 'ai')
const mine = computed(() => status.value === 'active' && handoff.value?.assignee === me.value)
const canReply = computed(() => mode.value === 'note' || mine.value)
const draftKey = computed(() => `${selected.value}-${mode.value}`)
const draft = computed({ get: () => drafts.value[draftKey.value] || '', set: (v: string) => (drafts.value[draftKey.value] = v) })
const headline = computed(() => {
  if (!d.value) return ''
  if (status.value === 'queued') return `排队中 · 第 ${handoff.value?.position ?? '?'} 位 · ${handoff.value?.reason_label}`
  if (status.value === 'active') return mine.value ? '由你接待中 · AI 已暂停' : `由 ${handoff.value?.assignee} 接待中`
  return 'AI 自动接待'
})

const listEl = ref<HTMLElement | null>(null)
const box = ref<HTMLTextAreaElement | null>(null)
const scroll = () => nextTick(() => listEl.value && (listEl.value.scrollTop = listEl.value.scrollHeight))
watch(() => [selected.value, d.value?.messages.length], scroll)
// 列表加载后默认选中第一条
watch(filtered, (rows) => {
  if (!selected.value && rows.length) selectedRaw.value = String(rows[0].conversation_id)
})

function select(id: number) {
  selectedRaw.value = String(id)
  mode.value = 'reply'
}
function setView(v: ListView) {
  view.value = v
  selectedRaw.value = ''
}
function setMode(next: 'reply' | 'note') {
  mode.value = next
  nextTick(() => box.value?.focus())
}

async function act<T>(fn: () => Promise<T>, done: (result: T) => string | void) {
  if (busy.value) return
  busy.value = true
  try {
    const result = await fn()
    const message = done(result)
    if (message) toast(message)
    await client.invalidateQueries({ queryKey: ['agent'] })
  } catch (e) {
    toast((e as Error).message)
  } finally {
    busy.value = false
  }
}

const accept = () =>
  act(() => acceptConversation(selected.value), () => {
    if (view.value === 'queued' || view.value === 'ai') view.value = 'mine'
    return status.value === 'ai' ? '已接管，AI 已暂停自动回复' : '已接入，可以回复顾客'
  })
const finish = () =>
  openModal({
    title: '结束本次人工接待',
    view: FinishModal,
    props: {
      onConfirm: () =>
        act(() => closeConversation(selected.value), (r) =>
          r.harvested ? `已结束接待，${r.harvested} 条问答已进入知识缺口待审` : '已结束接待，会话恢复 AI 接待'),
    },
  })
const transfer = () =>
  openModal({
    title: '转交会话',
    view: TransferModal,
    props: {
      current: handoff.value?.assignee ?? null,
      onConfirm: (to: string) => act(() => transferConversation(selected.value, to), () => `已转交给 ${to}`),
    },
  })
const newTicket = () =>
  d.value &&
  openModal({
    title: '新建工单',
    view: NewTicketModal,
    props: { conversationId: d.value.conversation_id, customer: d.value.user_id, title: card.value?.last_question?.slice(0, 60) ?? '' },
  })

async function send() {
  const text = draft.value.trim()
  if (!text) return toast('先输入内容')
  if (!canReply.value) return toast(status.value === 'active' ? '该会话由其他坐席接待' : '请先接入会话')
  const kind = mode.value
  const key = draftKey.value
  await act(() => postMessage(selected.value, text, kind), () => {
    drafts.value[key] = ''
    return kind === 'note' ? '已保存内部备注，仅团队可见' : undefined
  })
  box.value?.focus()
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}
const moodColor = (level?: string) => (level === 'angry' ? 'red' : level === 'upset' ? 'amber' : '')
const orderLabels: Record<string, string> = { order_id: '订单号', product_name: '商品', status: '订单状态', amount: '金额', created_at: '下单时间', logistics_status: '物流' }
</script>

<template>
  <div v-if="!allowed" class="page"><div class="notice amber">当前账号不是坐席，不能使用会话工作台。请使用坐席或管理员账号登录。</div></div>
  <div v-else class="desk">
    <section class="queue" aria-label="会话列表">
      <div class="queue-top">
        <div class="queue-title between">
          <h2>会话</h2>
          <span class="small muted">{{ filtered.length }} 条</span>
        </div>
        <label class="search"><Icon name="search" /><input v-model="search" aria-label="搜索会话" placeholder="顾客 ID、会话号或消息" /></label>
        <div class="queue-tabs" role="group" aria-label="会话筛选">
          <button v-for="[id, label, n] in tabs" :key="id" :class="{ active: view === id }" :aria-pressed="view === id" @click="setView(id)">
            {{ label }}<b v-if="n !== ''">{{ n }}</b>
          </button>
        </div>
      </div>
      <div class="queue-sub"><span>{{ view === 'queued' ? '按转入时间排序' : '最近活跃' }}</span><span>网页 · 拼多多</span></div>
      <div class="conversation-list">
        <p v-if="list.error.value" class="notice amber" style="margin: 12px">{{ list.error.value.message }}</p>
        <button v-for="x in filtered" :key="x.conversation_id" class="conversation-item" :class="{ active: x.conversation_id === selected }" :aria-pressed="x.conversation_id === selected" @click="select(x.conversation_id)">
          <Avatar :name="x.user_id" :color="x.status === 'queued' ? 'amber' : 'blue'" />
          <div class="conversation-copy">
            <div class="row">
              <strong>{{ x.user_id }}</strong><time>{{ shortTime(x.last_message?.created_at ?? x.handoff?.created_at) }}</time>
            </div>
            <p>{{ x.last_message?.content || '（暂无消息）' }}</p>
            <div class="row">
              <StatusPill :color="statusColor(x.status)">{{ statusText[x.status] }}</StatusPill
              ><StatusPill v-if="x.channel === 'pinduoduo'" color="red">{{ channelText[x.channel] }}</StatusPill
              ><span class="small muted">#{{ x.conversation_id }}<template v-if="x.handoff"> · {{ x.handoff.assignee ?? x.handoff.reason_label }}</template></span
              ><span v-if="x.status === 'queued'" class="unread" aria-label="待接待"></span>
            </div>
          </div>
        </button>
        <div v-if="!filtered.length && !list.isLoading.value && !list.error.value" class="empty"><Icon name="chat" />
          <p>{{ view === 'queued' ? '暂时没有排队的顾客' : '没有匹配的会话' }}</p>
        </div>
      </div>
      <div class="queue-footer"><Icon name="shield" /> 内部备注只在工作台显示，顾客看不到</div>
    </section>

    <section class="chat-area" aria-label="顾客会话">
      <template v-if="d">
        <header class="chat-header">
          <Avatar :name="d.user_id" color="blue" />
          <div>
            <h2>{{ d.user_id }} <span class="small muted">· {{ channelText[d.channel] ?? '网页' }} · 会话 #{{ d.conversation_id }}</span></h2>
            <div class="chat-meta"><span class="dot" :class="{ amber: status === 'queued' }"></span>{{ headline }}</div>
          </div>
          <button v-if="status !== 'active'" class="btn primary" :disabled="busy" @click="accept"><Icon name="headset" />{{ status === 'queued' ? '接入会话' : '接管会话' }}</button>
          <template v-else-if="mine || isAdmin">
            <button class="btn" :disabled="busy" @click="transfer">转交</button>
            <button class="btn" :disabled="busy" @click="finish"><Icon name="check" />结束接待</button>
          </template>
        </header>
        <div ref="listEl" class="chat-messages"><AgentMessages :messages="d.messages" :customer="d.user_id" /></div>
        <div v-if="card" class="summary-strip">
          <Icon name="spark" />
          <div>
            <b>交接摘要 · {{ card.reason_label }}</b>
            <p>{{ card.summary || card.last_question || '顾客没有留下问题描述' }}</p>
          </div>
        </div>
        <div class="composer">
          <div class="composer-box">
            <div class="composer-mode">
              <button :class="{ active: mode === 'reply' }" @click="setMode('reply')">回复顾客</button><button :class="{ active: mode === 'note' }" @click="setMode('note')">内部备注</button>
            </div>
            <textarea
              ref="box"
              v-model="draft"
              :aria-label="mode === 'note' ? '内部备注' : '回复内容'"
              :placeholder="canReply ? (mode === 'note' ? '添加仅团队可见的记录…' : '写下你的回复…') : status === 'active' ? '该会话由其他坐席接待，可以写内部备注' : '接入会话后即可回复顾客…'"
              maxlength="2000"
              @keydown="onKey"
            ></textarea>
            <div class="composer-foot">
              <button class="icon-btn" aria-label="新建工单" title="新建工单" @click="newTicket"><Icon name="ticket" /></button><span class="hint">Enter 发送 / Shift + Enter 换行</span
              ><button class="btn primary" :disabled="!canReply || busy" @click="send">{{ mode === 'note' ? '保存备注' : canReply ? '发送' : '请先接入' }} <Icon name="send" /></button>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="empty" style="margin: auto"><Icon name="chat" /><p>{{ detail.error.value?.message ?? (detail.isLoading.value ? '正在读取会话…' : '从左侧选择一个会话') }}</p></div>
    </section>

    <aside class="details">
      <div class="detail-head"><span>交接卡片</span><span class="muted">{{ card ? '转人工时生成' : '当前会话' }}</span></div>
      <template v-if="d">
        <section class="detail-section">
          <div class="detail-profile">
            <Avatar :name="d.user_id" color="blue" />
            <div>
              <b>{{ d.user_id }}</b>
              <p>Web 访客 · 会话 #{{ d.conversation_id }}</p>
            </div>
          </div>
          <div class="detail-row"><span>当前接待</span><span>{{ status === 'active' ? (mine ? `${me}（我）` : handoff?.assignee) : status === 'queued' ? '等待接入' : 'Minihelp 助手' }}</span></div>
          <div v-if="handoff" class="detail-row"><span>转人工时间</span><span>{{ shortTime(handoff.created_at) }}</span></div>
          <div v-if="card" class="detail-row"><span>用户情绪</span><StatusPill :color="moodColor(card.mood.level)">{{ card.mood.label }}</StatusPill></div>
          <p v-if="card?.mood.hits.length" class="small muted">关键词：{{ card.mood.hits.join('、') }}（规则判断，仅供参考）</p>
          <div v-if="card?.intent" class="detail-row"><span>识别意图</span><span>{{ card.intent }}</span></div>
        </section>
        <section v-if="card?.last_question" class="detail-section">
          <h3>顾客最后的问题</h3>
          <p class="small">{{ card.last_question }}</p>
        </section>
        <section v-if="card?.order" class="detail-section">
          <h3>关联订单</h3>
          <div class="order-tile">
            <div v-for="(v, k) in card.order" :key="k" class="detail-row"><span>{{ orderLabels[k] ?? k }}</span><span class="mono">{{ v }}</span></div>
          </div>
        </section>
        <section v-if="card?.evidence.length" class="detail-section">
          <h3>AI 检索到的资料</h3>
          <div v-for="(e, i) in card.evidence" :key="i" class="record">
            <span class="dot"></span>
            <div><b class="small">{{ e.title }}</b><small>{{ e.text }}</small></div>
          </div>
        </section>
        <section class="detail-section">
          <div class="between">
            <h3>相关工单</h3>
            <button class="text-button" @click="newTicket"><Icon name="plus" />新建</button>
          </div>
          <template v-if="d.tickets.length">
            <div v-for="t in d.tickets" :key="t.ticket_no" class="record">
              <span class="dot"></span>
              <div>
                <RouterLink class="table-actions" :to="{ path: '/tickets', query: { t: t.ticket_no } }">{{ t.title }}</RouterLink><small>{{ t.ticket_no }} · <StatusPill :color="ticketColor(t.status)">{{ t.status }}</StatusPill></small>
              </div>
            </div>
          </template>
          <p v-else class="small muted">暂时没有关联工单</p>
        </section>
        <div class="notice" style="font-size: 10px">接入后 AI 暂停自动回复；结束接待后恢复 AI，本次问答会进入知识缺口队列等待审核。</div>
      </template>
    </aside>
  </div>
</template>
