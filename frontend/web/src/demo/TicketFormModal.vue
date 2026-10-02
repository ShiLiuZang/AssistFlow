<!-- 新建工单 / 客户确认退货申请 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { closeModal } from '../composables/useModal'
import { toast } from '../composables/useToast'
import Avatar from './Avatar.vue'
import { demo, findConv, now } from './store'

const props = defineProps<{ id: number; fromClient?: boolean }>()
const c = computed(() => findConv(props.id) ?? demo.conversations[0])
const type = ref('退货')
const title = ref(c.value.id === 1 ? '猫砂盆退货申请' : c.value.subject)
const desc = ref(c.value.id === 1 ? '商品未使用，外包装已拆，想确认是否可以退货。' : '')

function submit() {
  const t = title.value.trim(),
    d = desc.value.trim()
  if (!t || !d) {
    toast('请完整填写标题和情况说明')
    return
  }
  const ticket = {
    id: `TK-${++demo.seq}`,
    customer: c.value.name,
    conv: c.value.id,
    title: t,
    type: type.value,
    status: 'open' as const,
    priority: '普通',
    time: '09-22 ' + now(),
    desc: d,
    history: ['由' + (props.fromClient ? '客户申请' : '客服会话') + '创建工单'],
  }
  demo.tickets.unshift(ticket)
  c.value.messages.push({ role: 'system', text: `已创建${ticket.type}工单 ${ticket.id} · 等待处理`, time: now() })
  closeModal()
  toast(`工单 ${ticket.id} 已创建，可在工单中心跟进`)
}
</script>

<template>
  <div class="modal-body">
    <div class="notice" :class="{ amber: fromClient }">
      {{ fromClient ? '提交后将生成售后工单，由客服确认条件和寄回方式。此操作不会直接退款。' : '工单将关联当前客户、会话和订单，便于后续追踪。' }}
    </div>
    <form id="ticket-form" @submit.prevent="submit">
      <div class="row" style="margin-bottom: 20px">
        <Avatar :name="c.name" :color="c.color" />
        <div>
          <h3>{{ c.name }}</h3>
          <p class="muted mono">{{ c.order }}</p>
        </div>
      </div>
      <label class="field"
        >工单类型<select v-model="type" name="type">
          <option v-for="t in ['退货', '换货', '补发', '物流', '咨询']" :key="t">{{ t }}</option>
        </select></label
      >
      <label class="field">问题标题<input v-model="title" name="title" required maxlength="70" /></label>
      <label class="field">情况说明<textarea v-model="desc" name="desc" required maxlength="1500" placeholder="描述商品情况和需要协助的事项"></textarea></label>
      <p class="field-hint">所有内容均为演示，不会提交给真实店铺。</p>
    </form>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">取消</button
    ><button class="btn primary" type="submit" form="ticket-form">{{ fromClient ? '确认提交申请' : '创建工单' }} <Icon name="arrow" /></button>
  </div>
</template>
