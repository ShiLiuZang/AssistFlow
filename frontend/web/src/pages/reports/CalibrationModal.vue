<script setup lang="ts">
import type { CalibrationBlock } from '../../api/types'
import VTable from '../../components/VTable.vue'
import ModalFoot from './ModalFoot.vue'
import { decimal } from './state'
defineProps<{ scored: NonNullable<CalibrationBlock['scored']> }>()
</script>

<template>
  <div class="modal-body">
    <VTable :heads="['样本 ID', '校准判断', '检索置信度']" :empty="!scored.length">
      <tr v-for="row in scored" :key="row.id">
        <td class="mono">{{ row.id }}</td>
        <td>{{ row.answerable === true ? '可回答' : row.answerable === false ? '应拒答' : '未标注' }}</td>
        <td class="mono">{{ decimal(row.score) }}</td>
      </tr>
    </VTable>
    <p class="field-hint section-gap">分数来自校准报告，不是回答正确率。当前只读，未修改运行阈值。</p>
  </div>
  <ModalFoot />
</template>
