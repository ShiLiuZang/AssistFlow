<script setup lang="ts">
import { computed } from 'vue'
import Icon from '../components/Icon.vue'
import StatusPill from '../components/StatusPill.vue'
import { closeModal } from '../composables/useModal'
import { showTicket } from './actions'
import { demo, ticketColor, ticketLabel } from './store'
const list = computed(() => demo.tickets.filter((t) => t.conv === 1))
</script>

<template>
  <div class="modal-body">
    <template v-if="list.length">
      <div v-for="t in list" :key="t.id" class="map-row" style="margin-bottom: 12px">
        <div class="between">
          <h3>{{ t.title }}</h3>
          <StatusPill :color="ticketColor(t)">{{ ticketLabel[t.status] }}</StatusPill>
        </div>
        <p class="mono muted">{{ t.id }}</p>
        <button class="table-actions" @click="showTicket(t.id, true)">查看进展 <Icon name="arrow" /></button>
      </div>
    </template>
    <div v-else class="empty">暂时没有服务记录<br />提交售后申请后，可以在这里跟进。</div>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">知道了</button></div>
</template>
