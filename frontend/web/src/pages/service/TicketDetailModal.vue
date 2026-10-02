<!-- 工单详情：处理记录与状态流转 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import StatusPill from '../../components/StatusPill.vue'
import { closeModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { TICKET_NEXT, changeTicket, shortTime, ticketColor, ticketDetail, type TicketStatus } from '../../api/agent'

const props = defineProps<{ ticketNo: string }>()
const client = useQueryClient()
const query = useQuery({ queryKey: ['agent', 'tickets', 'detail', props.ticketNo], queryFn: () => ticketDetail(props.ticketNo) })
const t = computed(() => query.data.value)
const note = ref('')
const busy = ref(false)
const actionLabel: Record<TicketStatus, string> = { 待处理: '退回待处理', 处理中: '开始处理', 已解决: '标记已解决', 已关闭: '关闭工单' }
const eventText = (e: NonNullable<NonNullable<typeof t.value>['events']>[number]) =>
  e.action === 'create' ? `创建工单${e.note ? ` · ${e.note}` : ''}` : e.action === 'status' ? `${e.from_status} → ${e.to_status}${e.note ? ` · ${e.note}` : ''}` : `备注：${e.note}`

async function change(status: TicketStatus) {
  if (!t.value || busy.value) return
  busy.value = true
  try {
    await changeTicket(t.value.ticket_no, status, note.value.trim())
    note.value = ''
    await client.invalidateQueries({ queryKey: ['agent'] })
    toast(status === t.value.status ? '已添加处理备注' : `工单已改为「${status}」`)
  } catch (e) {
    toast((e as Error).message)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="modal-body">
    <p v-if="query.isLoading.value" class="muted">正在读取工单…</p>
    <p v-else-if="query.error.value" class="notice amber">{{ query.error.value.message }}</p>
    <template v-else-if="t">
      <div class="between">
        <h3>{{ t.title }}</h3>
        <StatusPill :color="ticketColor(t.status)">{{ t.status }}</StatusPill>
      </div>
      <p class="muted mono small">{{ t.ticket_no }} · {{ t.ticket_type }} · {{ t.priority }} · 顾客 {{ t.user_id ?? '未知' }} · 会话 #{{ t.conversation_id }}</p>
      <p style="white-space: pre-line; margin: 12px 0">{{ t.description }}</p>
      <div class="detail-row"><span>负责人</span><span>{{ t.assignee ?? '未领取' }}</span></div>
      <div class="detail-row"><span>来源</span><span>{{ t.source === 'staff' ? '坐席创建' : '顾客在会话中确认' }}</span></div>
      <h3 style="margin-top: 16px">处理记录</h3>
      <div v-for="(e, i) in t.events ?? []" :key="i" class="record">
        <span class="dot"></span>
        <div><b class="small">{{ eventText(e) }}</b><small>{{ e.actor }} · {{ shortTime(e.created_at) }}</small></div>
      </div>
      <p v-if="!(t.events ?? []).length" class="small muted">这张工单创建于处理记录功能上线之前，没有历史记录。</p>
      <label v-if="t.status !== '已关闭'" class="field" style="margin-top: 16px">处理备注（可选）<textarea v-model="note" maxlength="1000" placeholder="例如：已联系仓库，等待补发单号"></textarea></label>
    </template>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">关闭</button>
    <template v-if="t">
      <button v-if="t.status !== '已关闭'" class="btn" :disabled="busy || !note.trim()" @click="change(t.status)">只添加备注</button>
      <button v-for="next in TICKET_NEXT[t.status]" :key="next" class="btn" :class="{ primary: next === '处理中' || next === '已解决' }" :disabled="busy" @click="change(next)">{{ actionLabel[next] }}</button>
    </template>
  </div>
</template>
