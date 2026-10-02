<!-- 观测与成本（对应 V2 admin-reports.js 的 observationPage） -->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getObservability } from '../api/endpoints'
import type { CalibrationBlock, CostBlock, TrendBlock } from '../api/types'
import DataPage from '../components/DataPage.vue'
import DataState from '../components/DataState.vue'
import { reportDataTime } from '../composables/useDataTime'
import { useUrlState } from '../composables/useUrlState'
import CalibrationTab from './reports/CalibrationTab.vue'
import CostTab from './reports/CostTab.vue'
import ReportEmpty from './reports/ReportEmpty.vue'
import TrendTab from './reports/TrendTab.vue'
import { openGuide } from './reports/guide'

const tabs = [
  ['cost', '意图消耗'],
  ['trend', '评估趋势'],
  ['calibration', '置信度校准'],
] as const
const tab = useUrlState('tab', 'cost')
const setTab = (key: string) => (tab.value = key)
const obs = useQuery({ queryKey: ['observability'], queryFn: getObservability })
watch(obs.dataUpdatedAt, reportDataTime, { immediate: true })

const key = computed(() => (['cost', 'trend', 'calibration'].includes(tab.value) ? (tab.value as 'cost' | 'trend' | 'calibration') : 'cost'))
const block = computed(() => obs.data.value?.[key.value])
const emptyTitles = { cost: '尚无成本报表', trend: '尚无可比较评测', calibration: '尚无校准报告' }
const state = computed(() => {
  const data = block.value
  if (!data || data.status === 'error') return ['当前报表读取失败', data?.hint || '服务未返回该报表，其他子页可独立查看。']
  const cost = data as CostBlock
  if (data.status !== 'ok' && !(key.value === 'cost' && cost.meta && cost.summary)) return [emptyTitles[key.value], data.hint || '尚未生成对应报告，读数保留为未知。']
  return null
})
</script>

<template>
  <DataPage page="observability">
    <template #actions>
      <button class="btn soft" @click="openGuide">报告运行说明</button>
    </template>

    <nav class="section-tabs" aria-label="观测与成本子页面">
      <button v-for="[k, label] in tabs" :key="k" :class="{ active: key === k }" :aria-current="key === k ? 'page' : 'false'" @click="setTab(k)">{{ label }}</button>
    </nav>
    <DataState v-if="!obs.data.value" :loading="obs.isPending.value" :error="obs.error.value" />
    <ReportEmpty v-else-if="state" :title="state[0]" :description="state[1]" />
    <CostTab v-else-if="key === 'cost'" :data="block as CostBlock" />
    <TrendTab v-else-if="key === 'trend'" :data="block as TrendBlock" />
    <CalibrationTab v-else :data="block as CalibrationBlock" />
  </DataPage>
</template>
