<script setup lang="ts">
import type { CostRow } from '../../api/types'
import ModalFoot from './ModalFoot.vue'
import PriceList from './PriceList.vue'
import ReportMeta from './ReportMeta.vue'
defineProps<{ row: CostRow }>()
</script>

<template>
  <div class="modal-body">
    <h3>{{ row.intent }}</h3>
    <ReportMeta
      :items="[
        ['请求', row.requests],
        ['生成调用', row.generations],
        ['用量未知', row.unknown_usage],
        ['未定价', row.unpriced],
        ['耗时样本', row.duration_samples],
      ]"
    />
    <h3>已定价小计</h3>
    <div class="section-gap"><PriceList :row="row" /></div>
    <p class="field-hint section-gap">价格版本：{{ row.price_versions?.join('、') || '未提供' }}</p>
    <p class="field-hint section-gap">
      只有已知用量且已定价的调用进入小计。未知用量不等于零，未定价不等于免费。P95 仅覆盖 {{ row.duration_samples ?? '未知数量的' }} 条有耗时记录的生成调用。
    </p>
  </div>
  <ModalFoot />
</template>
