<!-- 客户资料（对应 V2 service-panels.js 的 customersPage） -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import { openModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { newTicket, showOrder } from '../../demo/actions'
import Avatar from '../../demo/Avatar.vue'
import TicketCards from '../../demo/TicketCards.vue'
import { activeTickets, demo, findConv, match, now, orderState, view } from '../../demo/store'
import CustomerEditModal from './CustomerEditModal.vue'
import ServiceHeading from './ServiceHeading.vue'

const router = useRouter()
const list = computed(() =>
  demo.conversations.filter(
    (c) =>
      match(`${c.name} ${c.order} ${c.tags.join(' ')}`, view.customerQuery) &&
      (view.customerFilter === 'all' || (view.customerFilter === 'follow' && activeTickets(c).length) || (view.customerFilter === 'human' && c.status === 'human')),
  ),
)
const c = computed(() => findConv(view.customer) ?? demo.conversations[0])
const notes = computed(() => c.value.messages.filter((m) => m.role === 'note'))
const tabs = computed(() => [
  ['summary', '资料概况'],
  ['history', '会话记录'],
  ['notes', `内部备注${notes.value.length ? ` · ${notes.value.length}` : ''}`],
])
const roleName = (role: string) => ({ customer: c.value.name, staff: '周小雨', bot: 'Minihelp 助手', system: '服务记录' })[role as 'customer']
const note = ref('')
function reset() {
  view.customerQuery = ''
  view.customerFilter = 'all'
}
function saveNote() {
  const text = note.value.trim()
  if (!text) return toast('请填写备注内容')
  c.value.messages.push({ role: 'note', text, time: now() })
  note.value = ''
  toast('内部备注已保存，仅在团队视角显示')
}
function toConversation() {
  view.selected = c.value.id
  view.mode = 'reply'
  router.push('/workbench')
}
const edit = () => openModal({ title: `${c.value.name} · 编辑资料`, view: CustomerEditModal, props: { id: c.value.id } })
</script>

<template>
  <div class="page admin-page service-page">
    <ServiceHeading eyebrow="CUSTOMER CONTEXT" title="了解客户，再开始下一次对话。" desc="把资料、历史会话与售后进展放在一起。" />
    <div class="customer-workspace">
      <section class="panel customer-directory">
        <div class="panel-head">
          <h2>客户列表</h2>
          <span class="muted small">{{ demo.conversations.length }} 位演示客户</span>
        </div>
        <div class="directory-tools">
          <label class="search"><Icon name="search" /><input id="customer-search" v-model="view.customerQuery" aria-label="搜索客户资料" placeholder="客户、标签或订单" /></label>
          <div class="filter-row">
            <button
              v-for="[id, label] in [
                ['all', '全部'],
                ['follow', '待跟进'],
                ['human', '我接待的'],
              ]"
              :key="id"
              class="filter-chip"
              :class="{ active: view.customerFilter === id }"
              :aria-pressed="view.customerFilter === id"
              @click="view.customerFilter = id"
            >
              {{ label }}
            </button>
          </div>
        </div>
        <div id="customer-list" class="customer-list">
          <button v-for="x in list" :key="x.id" class="customer-item" :class="{ selected: x.id === view.customer }" :aria-pressed="x.id === view.customer" @click="view.customer = x.id">
            <Avatar :name="x.name" :color="x.color" /><span
              ><strong>{{ x.name }}</strong><small>{{ x.subject }}</small></span
            ><span v-if="activeTickets(x).length" class="pill amber">{{ activeTickets(x).length }} 待跟进</span><Icon v-else name="chevron" />
          </button>
          <div v-if="!list.length" class="empty">
            <p>没有符合条件的客户</p>
            <button class="btn" @click="reset">清除筛选</button>
          </div>
        </div>
      </section>
      <section class="panel customer-detail" aria-label="客户详情">
        <div class="customer-profile">
          <div class="row">
            <Avatar :name="c.name" :color="c.color" />
            <div>
              <h2>{{ c.name }}</h2>
              <p>客户 C-{{ String(c.id).padStart(4, '0') }} · Web 演示访客</p>
            </div>
          </div>
          <button class="btn" @click="edit">编辑资料</button>
        </div>
        <div class="customer-tags"><StatusPill v-for="t in c.tags" :key="t" color="neutral">{{ t }}</StatusPill></div>
        <nav class="section-tabs" aria-label="customer-detail子页面">
          <button v-for="[id, label] in tabs" :key="id" :class="{ active: view.customerTab === id }" :aria-pressed="view.customerTab === id" @click="view.customerTab = id">{{ label }}</button>
        </nav>
        <div class="customer-detail-body">
          <div v-if="view.customerTab === 'summary'" class="customer-context">
            <section>
              <div class="section-heading"><h3>服务上下文</h3><span>来自当前演示会话</span></div>
              <dl class="property-grid">
                <div><dt>咨询渠道</dt><dd>网站咨询</dd></div>
                <div><dt>当前接待</dt><dd>{{ c.status === 'human' ? '周小雨' : c.status === 'queued' ? '等待分配' : 'Minihelp 助手' }}</dd></div>
                <div><dt>联系偏好</dt><dd>{{ demo.preferences[c.id] || '优先站内回复' }}</dd></div>
                <div><dt>最近咨询</dt><dd>{{ c.time }} · {{ c.subject }}</dd></div>
              </dl>
              <div class="section-heading">
                <h3>关联订单</h3>
                <button class="text-button" @click="showOrder(c.id)">查看详情 <Icon name="arrow" /></button>
              </div>
              <div class="linked-order">
                <div class="image-placeholder">商品图待补</div>
                <div>
                  <strong>{{ c.product }}</strong><small class="mono">{{ c.order }}</small><span>¥ {{ c.amount }} · {{ orderState(c) }}</span>
                </div>
              </div>
            </section>
            <section>
              <div class="section-heading">
                <h3>关联工单</h3>
                <button class="text-button" @click="newTicket(c.id)"><Icon name="plus" />新建</button>
              </div>
              <TicketCards :conv="c" />
              <div class="quiet-note">工单、会话和客户资料共用同一组演示记录，处理状态会同步显示。</div>
            </section>
          </div>
          <template v-else-if="view.customerTab === 'history'">
            <div class="section-heading">
              <h3>当前会话记录</h3>
              <button class="btn" @click="toConversation">进入会话 <Icon name="arrow" /></button>
            </div>
            <div class="customer-history">
              <article v-for="(m, i) in c.messages.filter((x) => x.role !== 'note')" :key="i">
                <div><b>{{ roleName(m.role) }}</b><time>{{ m.time }}</time></div>
                <p>{{ m.text }}</p>
              </article>
            </div>
          </template>
          <template v-else>
            <div class="section-heading"><h3>内部备注</h3><span>仅团队可见</span></div>
            <form id="customer-note-form" class="note-compose" @submit.prevent="saveNote">
              <label for="customer-note">记录需要继续跟进的信息</label>
              <textarea id="customer-note" v-model="note" name="note" required maxlength="1000" placeholder="例如：客户希望工作日下午通过站内消息联系。"></textarea>
              <button class="btn primary" type="submit">保存备注</button>
            </form>
            <div v-if="notes.length" class="customer-history">
              <article v-for="(m, i) in [...notes].reverse()" :key="i">
                <div><b>周小雨</b><time>{{ m.time }}</time></div>
                <p>{{ m.text }}</p>
              </article>
            </div>
            <div v-else class="empty"><p>暂无内部备注，保存后也能在客服会话中看到。</p></div>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>
