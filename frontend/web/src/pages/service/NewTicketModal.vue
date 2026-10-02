<!-- 坐席新建工单：关联当前会话与顾客 -->
<script setup lang="ts">
import { ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import Icon from '../../components/Icon.vue'
import { closeModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { TICKET_TYPES, createTicket } from '../../api/agent'

const props = defineProps<{ conversationId: number; customer: string; title?: string; description?: string }>()
const client = useQueryClient()
const type = ref('咨询')
const priority = ref('普通')
const title = ref(props.title ?? '')
const description = ref(props.description ?? '')
const busy = ref(false)
const error = ref('')

async function submit() {
  if (!title.value.trim() || !description.value.trim()) {
    error.value = '请填写标题和情况说明'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const ticket = await createTicket({
      conversation_id: props.conversationId, ticket_type: type.value, title: title.value.trim(),
      description: description.value.trim(), priority: priority.value,
    })
    client.invalidateQueries({ queryKey: ['agent'] })
    closeModal()
    toast(`工单 ${ticket.ticket_no} 已创建，可在工单中心跟进`)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="modal-body">
    <div class="notice">工单关联会话 #{{ conversationId }} 与顾客 {{ customer }}。创建工单不代表已退款，实际处理以业务系统为准。</div>
    <form id="agent-ticket-form" @submit.prevent="submit">
      <div class="row" style="gap: 12px">
        <label class="field" style="flex: 1">工单类型<select v-model="type"><option v-for="t in TICKET_TYPES" :key="t">{{ t }}</option></select></label>
        <label class="field" style="flex: 1">优先级<select v-model="priority"><option>普通</option><option>优先</option></select></label>
      </div>
      <label class="field">问题标题<input v-model="title" required maxlength="120" /></label>
      <label class="field">情况说明<textarea v-model="description" required maxlength="2000" placeholder="描述顾客诉求、商品情况和需要跟进的事项"></textarea></label>
      <p v-if="error" class="notice amber" role="alert">{{ error }}</p>
    </form>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">取消</button
    ><button class="btn primary" type="submit" form="agent-ticket-form" :disabled="busy">{{ busy ? '提交中…' : '创建工单' }} <Icon name="arrow" /></button>
  </div>
</template>
