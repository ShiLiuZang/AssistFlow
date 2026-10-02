<!-- 订单详情（对应 V2 servicePanels.showOrder） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '../components/Icon.vue'
import StatusPill from '../components/StatusPill.vue'
import { closeModal } from '../composables/useModal'
import { newTicket } from './actions'
import TicketCards from './TicketCards.vue'
import { findConv, orderColor, orderState } from './store'

const props = defineProps<{ id: number }>()
const route = useRoute()
const c = computed(() => findConv(props.id)!)
const isClient = computed(() => route.meta.surface === 'client')
const delivery = computed(() =>
  c.value.id === 2
    ? [
        ['已支付', '演示记录'],
        ['已交承运商', '演示记录'],
        ['运输信息超过 48 小时未更新', '待客服核查'],
      ]
    : [4, 6].includes(c.value.id)
      ? [
          ['已支付', '演示记录'],
          ['等待仓库发货', '尚无物流单号'],
        ]
      : [
          ['已支付', '演示记录'],
          ['已发货', '演示记录'],
          ['已签收', '演示记录'],
        ],
)
</script>

<template>
  <div class="modal-body">
    <div class="between">
      <StatusPill :color="orderColor(c)">{{ orderState(c) }}</StatusPill><span class="small muted">Web 演示订单</span>
    </div>
    <div class="linked-order">
      <div class="image-placeholder">商品图待补</div>
      <div>
        <h3>{{ c.product }}</h3>
        <small class="mono">{{ c.order }}</small><span>数量 1 · 实付 ¥ {{ c.amount }}</span>
      </div>
    </div>
    <dl class="property-grid">
      <div><dt>客户</dt><dd>{{ c.name }}</dd></div>
      <div><dt>收货信息</dt><dd>待接入业务系统</dd></div>
    </dl>
    <h3>物流进展</h3>
    <div class="timeline">
      <div v-for="[title, time] in delivery" :key="title" class="timeline-item">{{ title }}<small>{{ time }}</small></div>
    </div>
    <template v-if="!isClient">
      <div class="section-heading"><h3>售后跟进</h3></div>
      <TicketCards :conv="c" />
    </template>
    <div class="quiet-note">本页为示例。申请售后后会创建待处理工单，是否符合退货条件仍需审核。</div>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">关闭</button
    ><button class="btn primary" @click="newTicket(c.id, isClient)"><Icon name="ticket" />{{ isClient ? '申请售后' : '创建售后工单' }}</button>
  </div>
</template>
