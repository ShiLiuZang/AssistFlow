<!-- 验收项依据 -->
<script setup lang="ts">
import type { AcceptanceBlock } from '../../api/types'
import { closeModal } from '../../composables/useModal'
import ModalFoot from '../reports/ModalFoot.vue'
import GateStatus from '../classification/GateStatus.vue'
import MetaRow from '../classification/MetaRow.vue'
const props = defineProps<{ block: AcceptanceBlock; onReport: (key: string) => void; onJobs: () => void }>()
function report() {
  closeModal()
  props.onReport(props.block.key)
}
</script>

<template>
  <div class="modal-body">
    <GateStatus :status="block.status" />
    <h3 class="section-gap">{{ block.headline }}</h3>
    <p class="section-gap">{{ block.note }}</p>
    <MetaRow :items="[['关联作业', (block.jobs || []).join('、') || '未提供']]" />
    <p class="field-hint">这是后端已有验收摘要；相关报告在对应子页查看。作业入口可核对执行条件，再确认启动。</p>
    <div class="section-gap"><button class="btn" @click="report">查看对应报告</button><button class="btn" @click="onJobs">查看登记作业</button></div>
  </div>
  <ModalFoot />
</template>
