<!-- 关联工单行（客户资料与订单详情共用） -->
<script setup lang="ts">
import Icon from '../components/Icon.vue'
import StatusPill from '../components/StatusPill.vue'
import { showTicket } from './actions'
import { relatedTickets, ticketColor, ticketLabel, type Conversation } from './store'
defineProps<{ conv: Conversation }>()
</script>

<template>
  <template v-if="relatedTickets(conv).length">
    <button v-for="t in relatedTickets(conv)" :key="t.id" class="relation-row" @click="showTicket(t.id)">
      <span class="relation-icon"><Icon name="ticket" /></span
      ><span
        ><strong>{{ t.title }}</strong><small>{{ t.id }} · {{ t.type }}</small></span
      ><StatusPill :color="ticketColor(t)">{{ ticketLabel[t.status] }}</StatusPill><Icon name="chevron" />
    </button>
  </template>
  <div v-else class="empty"><p>暂时没有关联工单</p></div>
</template>
