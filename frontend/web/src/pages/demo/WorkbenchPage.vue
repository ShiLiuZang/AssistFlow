<!-- 会话工作台（对应 V2 prototype.js 的 workbench） -->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import { openModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { newTicket, showOrder, showTicket } from '../../demo/actions'
import Avatar from '../../demo/Avatar.vue'
import ChatMessages from '../../demo/ChatMessages.vue'
import { demo, findConv, now, orderColor, orderState, view, type Conversation } from '../../demo/store'
import FinishModal from './FinishModal.vue'

const router = useRouter()
const c = computed(() => findConv(view.selected) ?? demo.conversations[0])
const canSend = computed(() => c.value.status === 'human' || view.mode === 'note')
const draftKey = computed(() => `${c.value.id}-${view.mode}`)
const draft = computed({ get: () => view.drafts[draftKey.value] || '', set: (v: string) => (view.drafts[draftKey.value] = v) })
const queues = computed(() => [
  ['all', '全部', demo.conversations.length],
  ['waiting', '待接待', demo.conversations.filter((x) => x.status === 'queued').length],
  ['mine', '我的', demo.conversations.filter((x) => x.status === 'human').length],
])
const filtered = computed(() =>
  demo.conversations.filter(
    (x) => (view.queue === 'all' || x.status === (view.queue === 'waiting' ? 'queued' : 'human')) && `${x.name}${x.subject}${x.order}`.toLowerCase().includes(view.search.toLowerCase()),
  ),
)
const lastText = (x: Conversation) => x.messages.filter((m) => m.role !== 'system').at(-1)?.text || x.subject
const related = computed(() => demo.tickets.filter((t) => t.conv === c.value.id))
const statusText = (x: Conversation) => (x.status === 'queued' ? '待接待' : x.status === 'human' ? '人工接待' : 'AI 接待')
const statusColor = (x: Conversation) => (x.status === 'queued' ? 'amber' : x.status === 'human' ? 'blue' : '')

const list = ref<HTMLElement | null>(null)
const box = ref<HTMLTextAreaElement | null>(null)
const scroll = () => nextTick(() => list.value && (list.value.scrollTop = list.value.scrollHeight))
// 与 V2 一致：只在新增消息后滚到底部，切换会话时保持在顶部
watch(() => c.value.messages.length, scroll)

function select(id: number) {
  view.selected = id
  view.mode = 'reply'
}
function setMode(mode: 'reply' | 'note') {
  view.mode = mode
  nextTick(() => box.value?.focus())
}
function takeover() {
  c.value.status = 'human'
  c.value.messages.push({ role: 'system', text: '周小雨已接管会话 · AI 自动回复已暂停', time: now() })
  toast('已接管，可回复客户或使用 AI 草稿')
}
function finish() {
  openModal({
    title: '结束本次人工接待',
    view: FinishModal,
    props: {
      onConfirm: () => {
        c.value.status = 'auto'
        c.value.messages.push({ role: 'system', text: '本次人工接待结束 · 已恢复 AI 接待', time: now() })
        toast('会话已恢复 AI 接待，工单继续保留')
      },
    },
  })
}
function aiDraft() {
  if (view.mode === 'note') {
    toast('请切换到回复客户后使用 AI 辅助')
    return
  }
  view.drafts[`${c.value.id}-reply`] =
    c.value.id === 1
      ? '您好，我来帮您确认。若商品未使用且配件齐全，我们可以先为您登记退货申请。请保留现有包装，并说明包装是否有破损，我会进一步核实寄回要求。'
      : '您好，我已经收到您的问题，将结合订单信息为您核实具体情况，请稍候。'
  box.value?.focus()
  toast('已填入预设辅助草稿，请确认后发送')
}
function send() {
  const text = draft.value.trim()
  if (!text) {
    toast('先输入回复内容')
    return
  }
  if (view.mode === 'reply' && c.value.status !== 'human') {
    toast('请先接管会话')
    return
  }
  c.value.messages.push({ role: view.mode === 'note' ? 'note' : 'staff', text, time: now() })
  c.value.time = now()
  draft.value = ''
  box.value?.focus()
  toast(view.mode === 'note' ? '已保存内部备注，仅团队可见' : c.value.id === 1 ? '已回复，可切换客户咨询页查看' : '演示回复已发送')
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}
function customerDetails() {
  view.customer = c.value.id
  view.customerQuery = ''
  view.customerFilter = 'all'
  view.customerTab = 'summary'
  router.push('/customers')
}
</script>

<template>
  <div class="desk">
    <section class="queue" aria-label="会话列表">
      <div class="queue-top">
        <div class="queue-title between">
          <h2>会话</h2>
          <span class="small muted">{{ demo.conversations.length }} 条</span>
        </div>
        <label class="search"><Icon name="search" /><input id="conversation-search" v-model="view.search" aria-label="搜索会话" placeholder="搜索客户或订单" /><span class="key">⌘K</span></label>
        <div class="queue-tabs" role="group" aria-label="会话筛选">
          <button v-for="[id, label, n] in queues" :key="id" :class="{ active: view.queue === id }" :aria-pressed="view.queue === id" @click="view.queue = String(id)">
            {{ label }}<b>{{ n }}</b>
          </button>
        </div>
      </div>
      <div class="queue-sub"><span>最近活跃</span><span>Web 渠道</span></div>
      <div id="conversation-list" class="conversation-list">
        <button v-for="x in filtered" :key="x.id" class="conversation-item" :class="{ active: x.id === view.selected }" :aria-pressed="x.id === view.selected" @click="select(x.id)">
          <Avatar :name="x.name" :color="x.color" />
          <div class="conversation-copy">
            <div class="row">
              <strong>{{ x.name }}</strong><time>{{ x.time }}</time>
            </div>
            <p>{{ lastText(x) }}</p>
            <div class="row">
              <StatusPill :color="statusColor(x)">{{ statusText(x) }}</StatusPill><span class="small muted">{{ x.subject }}</span
              ><span v-if="x.status === 'queued'" class="unread" aria-label="待接待"></span>
            </div>
          </div>
        </button>
        <div v-if="!filtered.length" class="empty"><Icon name="search" />
          <p>没有匹配的会话</p>
        </div>
      </div>
      <div class="queue-footer"><Icon name="shield" /> 客户消息与团队备注分开显示</div>
    </section>
    <section class="chat-area" aria-label="客户会话">
      <header class="chat-header">
        <Avatar :name="c.name" :color="c.color" />
        <div>
          <h2>{{ c.name }}</h2>
          <div class="chat-meta">
            <span class="dot" :class="{ amber: c.status === 'queued' }"></span>{{ c.status === 'queued' ? '等待人工接待' : c.status === 'human' ? '由你接待中' : 'AI 自动接待' }}<span>·</span>Web 咨询
          </div>
        </div>
        <button v-if="c.status !== 'human'" class="btn primary" @click="takeover"><Icon name="headset" />接管会话</button>
        <button v-else class="btn" @click="finish"><Icon name="check" />结束接待</button>
        <button class="icon-btn" aria-label="查看客户资料" @click="customerDetails"><Icon name="info" /></button>
      </header>
      <div id="staff-messages" ref="list" class="chat-messages"><ChatMessages :conv="c" /></div>
      <div class="summary-strip">
        <Icon name="spark" />
        <div>
          <b>接待提示</b>
          <p>{{ c.id === 1 ? '客户希望确认拆封包装是否影响退货，建议先核实商品与配件状态。' : '可结合客户消息与订单信息继续跟进。涉及业务操作时，请创建工单。' }}</p>
        </div>
      </div>
      <div class="composer">
        <div class="composer-box">
          <div class="composer-mode">
            <button :class="{ active: view.mode === 'reply' }" @click="setMode('reply')">回复客户</button><button :class="{ active: view.mode === 'note' }" @click="setMode('note')">内部备注</button>
          </div>
          <textarea
            id="staff-draft"
            ref="box"
            v-model="draft"
            :aria-label="view.mode === 'note' ? '内部备注' : '回复内容'"
            :placeholder="canSend ? (view.mode === 'note' ? '添加仅团队可见的记录…' : '写下你的回复…') : '接管会话后即可回复客户…'"
            maxlength="2000"
            @keydown="onKey"
          ></textarea>
          <div class="composer-foot">
            <button class="text-button" @click="aiDraft"><Icon name="spark" /> AI 辅助</button
            ><button class="icon-btn" aria-label="新建工单" @click="newTicket(c.id)"><Icon name="ticket" /></button><span class="hint">Enter 发送 / Shift + Enter 换行</span
            ><button class="btn primary" :disabled="!canSend" @click="send">{{ view.mode === 'note' ? '保存备注' : canSend ? '发送' : '请先接管' }} <Icon name="send" /></button>
          </div>
        </div>
      </div>
    </section>
    <aside class="details">
      <div class="detail-head"><span>客户资料</span><span class="muted">当前会话</span></div>
      <section class="detail-section">
        <div class="detail-profile">
          <Avatar :name="c.name" :color="c.color" />
          <div>
            <b>{{ c.name }}</b>
            <p>Web 访客 · 演示客户</p>
          </div>
        </div>
        <div class="detail-row"><span>当前接待</span><span>{{ c.status === 'human' ? '周小雨（我）' : c.status === 'queued' ? '等待分配' : 'Minihelp 助手' }}</span></div>
        <div class="detail-row"><span>最近到访</span><span>今天 {{ c.time }}</span></div>
        <div class="detail-tags"><StatusPill v-for="t in c.tags" :key="t" color="neutral">{{ t }}</StatusPill></div>
      </section>
      <section class="detail-section">
        <h3>关联订单</h3>
        <div class="order-tile">
          <div class="row">
            <div class="image-placeholder">商品图待补</div>
            <div>
              <strong>{{ c.product }}</strong>
              <p>数量 1 · ¥ {{ c.amount }}</p>
            </div>
          </div>
          <div class="detail-row"><span>订单状态</span><StatusPill :color="orderColor(c)">{{ orderState(c) }}</StatusPill></div>
          <div class="detail-row"><span>订单编号</span><span class="mono">{{ c.order.slice(-10) }}</span></div>
          <button class="btn" @click="showOrder(c.id)">查看订单详情 <Icon name="arrow" /></button>
        </div>
      </section>
      <section class="detail-section">
        <div class="between">
          <h3>相关工单</h3>
          <button class="text-button" @click="newTicket(c.id)"><Icon name="plus" />新建</button>
        </div>
        <template v-if="related.length">
          <div v-for="t in related" :key="t.id" class="record">
            <span class="dot"></span>
            <div>
              <button class="table-actions" @click="showTicket(t.id)">{{ t.title }}</button><small>{{ t.id }} · {{ t.status === 'resolved' ? '已解决' : t.status === 'working' ? '处理中' : '待处理' }}</small>
            </div>
          </div>
        </template>
        <p v-else class="small muted">暂时没有关联工单</p>
      </section>
      <div class="notice" style="font-size: 10px">接管后，AI 将暂停自动回复。你仍可使用 AI 辅助起草。</div>
    </aside>
  </div>
</template>
