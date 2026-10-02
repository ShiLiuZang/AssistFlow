<!-- 工单中心（对应 V2 prototype.js 的 ticketPage） -->
<script setup lang="ts">
import { computed } from 'vue'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import VStat from '../../components/VStat.vue'
import { newTicket, showTicket } from '../../demo/actions'
import { demo, ticketColor, ticketLabel, view } from '../../demo/store'

const count = (s: string) => demo.tickets.filter((t) => t.status === s).length
const rows = computed(() =>
  demo.tickets.filter((t) => (view.ticketFilter === 'all' || t.status === view.ticketFilter) && `${t.id}${t.title}${t.customer}`.includes(view.ticketSearch)),
)
const filters = [
  ['all', '全部工单'],
  ['open', '待处理'],
  ['working', '处理中'],
  ['resolved', '已解决'],
]
</script>

<template>
  <div class="page">
    <div class="page-title between">
      <div>
        <div class="eyebrow" style="margin-bottom: 6px">SERVICE TICKETS</div>
        <h1>把问题跟进到解决。</h1>
        <p>让每一笔售后有负责人、有进展、有结果。</p>
      </div>
      <button class="btn primary" @click="newTicket(view.selected)"><Icon name="plus" />新建工单</button>
    </div>
    <div class="stat-strip">
      <VStat label="全部工单" :value="demo.tickets.length" unit="笔" foot="演示业务记录" />
      <VStat label="待处理" :value="count('open')" unit="笔" foot="需要客服领取" />
      <VStat label="处理中" :value="count('working')" unit="笔" foot="保持进展同步" />
      <VStat label="已解决" :value="count('resolved')" unit="笔" foot="可查看处理记录" />
    </div>
    <section class="panel">
      <div class="panel-head">
        <h2>工单列表</h2>
        <span class="small muted">会话与订单关联</span>
      </div>
      <div class="panel-toolbar">
        <div class="ticket-filter">
          <button v-for="[id, label] in filters" :key="id" class="filter-chip" :class="{ active: view.ticketFilter === id }" @click="view.ticketFilter = id">{{ label }}</button>
        </div>
        <label class="search"><Icon name="search" /><input id="ticket-search" v-model="view.ticketSearch" aria-label="搜索工单" placeholder="编号、标题或客户" /></label>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>工单</th>
              <th>客户</th>
              <th>状态</th>
              <th>优先级</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody id="ticket-rows" class="ticket-rows">
            <tr v-for="t in rows" :key="t.id">
              <td>
                <button class="table-actions table-title" @click="showTicket(t.id)">{{ t.title }}</button><span class="table-sub mono">{{ t.id }} · {{ t.type }}</span>
              </td>
              <td>{{ t.customer }}</td>
              <td><StatusPill :color="ticketColor(t)">{{ ticketLabel[t.status] }}</StatusPill></td>
              <td><span v-if="t.priority === '优先'" class="priority"></span>{{ t.priority }}</td>
              <td class="muted">{{ t.time }}</td>
              <td><button class="table-actions" @click="showTicket(t.id)">跟进 <Icon name="chevron" /></button></td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="6"><div class="empty">当前没有匹配工单</div></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="panel-footer"><span>共 {{ demo.tickets.length }} 笔工单</span><span>本页状态仅保留在当前预览中</span></div>
    </section>
    <div class="notice" style="margin-top: 22px"><Icon name="info" /> 退货工单负责记录申请和跟进。创建工单并不表示已退款，实际支付结果将在正式业务链路中核验。</div>
  </div>
</template>
