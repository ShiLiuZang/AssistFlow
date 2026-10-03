<!-- 工单中心（真实接口）：按状态筛选、搜索、查看处理记录并流转状态 -->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import VStat from '../../components/VStat.vue'
import { openModal } from '../../composables/useModal'
import { useUrlState } from '../../composables/useUrlState'
import { hasRole } from '../../auth/session'
import { TICKET_STATUSES, agentSummary, listTickets, shortTime, ticketColor, type TicketStatus } from '../../api/agent'
import TicketDetailModal from './TicketDetailModal.vue'

const allowed = computed(() => hasRole('agent'))
const filter = useUrlState('status', '')
const opened = useUrlState('t', '')
const search = ref('')
const q = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  clearTimeout(timer)
  timer = setTimeout(() => (q.value = value), 300)
})
const summary = useQuery({ queryKey: ['agent', 'summary'], queryFn: agentSummary, enabled: allowed })
const rows = useQuery({
  queryKey: computed(() => ['agent', 'tickets', filter.value, q.value]),
  queryFn: () => listTickets(filter.value as TicketStatus | '', q.value.trim()),
  enabled: allowed,
})
const counts = computed(() => summary.data.value?.tickets)
const total = computed(() => (counts.value ? Object.values(counts.value).reduce((a, b) => a + b, 0) : ''))

function show(no: string) {
  opened.value = no
  openModal({ title: '工单详情', view: TicketDetailModal, props: { ticketNo: no } })
}
// 从工作台的工单链接进入时直接打开详情
onMounted(() => opened.value && show(opened.value))
</script>

<template>
  <div class="page">
    <div class="page-title between">
      <div>
        <div class="eyebrow" style="margin-bottom: 6px">SERVICE TICKETS</div>
        <h1>把问题跟进到解决。</h1>
        <p>坐席在会话中创建的工单和顾客确认提交的售后申请都在这里。</p>
      </div>
    </div>
    <div v-if="!allowed" class="notice amber">当前账号不是坐席，不能查看工单。请使用坐席或管理员账号登录。</div>
    <template v-else>
      <div class="stat-strip">
        <VStat label="全部工单" :value="total" unit="笔" foot="本库工单" />
        <VStat label="待处理" :value="counts?.['待处理'] ?? ''" unit="笔" foot="需要坐席领取" />
        <VStat label="处理中" :value="counts?.['处理中'] ?? ''" unit="笔" foot="保持进展同步" />
        <VStat label="已解决" :value="counts?.['已解决'] ?? ''" unit="笔" foot="可查看处理记录" />
      </div>
      <section class="panel">
        <div class="panel-head">
          <h2>工单列表</h2>
          <span class="small muted">最近 100 笔</span>
        </div>
        <div class="panel-toolbar">
          <div class="ticket-filter">
            <button class="filter-chip" :class="{ active: !filter }" @click="filter = ''">全部工单</button>
            <button v-for="s in TICKET_STATUSES" :key="s" class="filter-chip" :class="{ active: filter === s }" @click="filter = s">{{ s }}</button>
          </div>
          <label class="search"><Icon name="search" /><input v-model="search" aria-label="搜索工单" placeholder="编号、标题、顾客" /></label>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>工单</th>
                <th>顾客</th>
                <th>状态</th>
                <th>优先级</th>
                <th>负责人</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody class="ticket-rows">
              <tr v-for="t in rows.data.value ?? []" :key="t.ticket_no">
                <td>
                  <button class="table-actions table-title" @click="show(t.ticket_no)">{{ t.title }}</button><span class="table-sub mono">{{ t.ticket_no }} · {{ t.ticket_type }} · {{ t.source === 'staff' ? '坐席创建' : '顾客确认' }}</span>
                </td>
                <td>{{ t.user_id ?? '—' }}</td>
                <td><StatusPill :color="ticketColor(t.status)">{{ t.status }}</StatusPill></td>
                <td><span v-if="t.priority === '优先'" class="priority"></span>{{ t.priority }}</td>
                <td>{{ t.assignee ?? '未领取' }}</td>
                <td class="muted">{{ shortTime(t.updated_at) }}</td>
                <td><button class="table-actions" @click="show(t.ticket_no)">跟进 <Icon name="chevron" /></button></td>
              </tr>
              <tr v-if="rows.error.value">
                <td colspan="7"><div class="empty">{{ rows.error.value.message }}</div></td>
              </tr>
              <tr v-else-if="!rows.isLoading.value && !(rows.data.value ?? []).length">
                <td colspan="7"><div class="empty">当前没有匹配工单</div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <div class="notice" style="margin-top: 22px"><Icon name="info" /> 工单负责记录申请和跟进。创建工单不代表已退款，实际支付结果以业务系统为准。</div>
    </template>
  </div>
</template>
