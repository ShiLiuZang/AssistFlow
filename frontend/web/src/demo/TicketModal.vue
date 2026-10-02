<!-- 工单详情：领取 / 记录处理结果 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../components/Icon.vue'
import StatusPill from '../components/StatusPill.vue'
import { closeModal } from '../composables/useModal'
import { toast } from '../composables/useToast'
import { demo, findConv, ticketColor, ticketLabel } from './store'

const props = defineProps<{ id: string; fromClient?: boolean }>()
const t = computed(() => demo.tickets.find((x) => x.id === props.id)!)
const c = computed(() => findConv(t.value.conv))
const resolution = ref('')
const input = ref<HTMLTextAreaElement | null>(null)

function advance() {
  if (t.value.status === 'open') {
    t.value.status = 'working'
    t.value.history.push('周小雨已领取工单')
  } else if (t.value.status === 'working') {
    const result = resolution.value.trim()
    if (!result) {
      toast('请填写处理结果')
      input.value?.focus()
      return
    }
    t.value.status = 'resolved'
    t.value.history.push(`处理结果：${result}`)
  }
  resolution.value = ''
  toast('工单状态已更新')
}
</script>

<template>
  <div class="modal-body">
    <div class="between" style="margin-bottom: 20px">
      <span class="mono muted">{{ t.id }}</span><StatusPill :color="ticketColor(t)">{{ ticketLabel[t.status] }}</StatusPill>
    </div>
    <div class="detail-row"><span>关联客户</span><span>{{ t.customer }}</span></div>
    <div class="detail-row"><span>关联订单</span><span class="mono">{{ c?.order }}</span></div>
    <div class="detail-row"><span>负责客服</span><span>{{ t.status === 'open' ? '等待领取' : '周小雨' }}</span></div>
    <div class="preview-text" style="margin-top: 16px; white-space: pre-line">{{ t.desc }}</div>
    <div class="timeline">
      <div v-for="(h, i) in t.history" :key="i" class="timeline-item">{{ h }}<small>演示处理记录</small></div>
    </div>
    <template v-if="!fromClient && t.status === 'working'">
      <label class="field">处理结果<textarea id="resolution" ref="input" v-model="resolution" placeholder="记录处理结果，方便客户和团队追踪" maxlength="1000"></textarea></label>
      <p class="field-hint">结果会显示在客户的服务记录中，请勿填写内部信息。</p>
    </template>
    <p v-if="fromClient" class="muted">您可在服务记录中查看进展，实际退款以支付渠道结果为准。</p>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">关闭</button
    ><button v-if="!fromClient && t.status !== 'resolved'" class="btn primary" @click="advance">{{ t.status === 'open' ? '领取工单' : '标记已解决' }} <Icon name="check" /></button>
  </div>
</template>
