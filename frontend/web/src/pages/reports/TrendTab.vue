<!-- 评估趋势：只比较服务端判定可比较的运行 -->
<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import type { EvalRun, TrendBlock } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VTable from '../../components/VTable.vue'
import { openModal } from '../../composables/useModal'
import ReportEmpty from './ReportEmpty.vue'
import ReportMeta from './ReportMeta.vue'
import RunModal from './RunModal.vue'
import TrendChart from './TrendChart.vue'
import { decimal, finite, listStamp, name, percent, reportUI } from './state'

const props = defineProps<{ data: TrendBlock }>()
const runs = computed(() => props.data.runs ?? [])
const options = computed(() => {
  const list = [
    ['mrr', 'MRR'],
    ['recall_at_k', '召回率'],
    ['refusal_accuracy', '拒答准确率'],
    ['keyword_coverage', '关键词覆盖率'],
  ]
  if (runs.value.some((row) => finite(row.metrics?.faithfulness))) list.push(['faithfulness', '忠实度'])
  return list
})
watchEffect(() => {
  if (!options.value.some(([key]) => key === reportUI.trendMetric)) reportUI.trendMetric = 'mrr'
})
const latest = computed(() => runs.value[0])
const setMetric = (key: string) => (reportUI.trendMetric = key)
const statusText = (s: string) => (s === 'completed' ? '评测完成' : s === 'partial' ? '部分完成' : s || '未知')
const showRun = (run: EvalRun) => openModal({ title: '固定集运行明细', view: RunModal, props: { run }, cls: 'report-dialog' })
</script>

<template>
  <ReportEmpty v-if="!runs.length" title="尚无可比较运行" description="本次响应没有提供可比较的评测记录。" />
  <template v-else>
    <ReportMeta
      :items="[
        ['数据集', latest.dataset_version],
        ['配置版本', latest.config_version],
        ['策略', name(latest.strategy)],
        ['Top K', latest.top_k],
        ['可比较运行', runs.length],
        ['本次省略不可比', data.omitted_incomparable],
      ]"
    />
    <div class="notice report-note">{{ data.hint || '仅展示服务端判定可比较的运行。' }} 当前接口最多读取最近 10 次运行后筛选，不代表全部历史。</div>
    <VPanel title="可比较评测记录">
      <template #extra><StatusPill color="neutral">{{ runs.length === 1 ? '单次读数' : '可比较记录' }}</StatusPill></template>
      <div class="panel-toolbar">
        <button v-for="[key, label] in options" :key="key" class="filter-chip" :class="{ active: reportUI.trendMetric === key }" :aria-pressed="reportUI.trendMetric === key" @click="setMetric(key)">
          {{ label }}
        </button>
      </div>
      <TrendChart :runs="runs" :metric="reportUI.trendMetric" :label="options.find(([id]) => id === reportUI.trendMetric)?.[1] || reportUI.trendMetric" />
    </VPanel>
    <div class="section-gap">
      <VPanel title="运行明细">
        <VTable :heads="['运行与时间', '知识修订', '状态', '召回率', 'MRR', '拒答准确率', '关键词覆盖', '调用失败', '操作']" :empty="!runs.length">
          <tr v-for="run in runs" :key="run.id">
            <td><strong class="mono">RUN-{{ run.id }}</strong><span class="table-sub">{{ listStamp(run.created_at) }}</span></td>
            <td>{{ run.kb_revision ?? '未标注' }}</td>
            <td><StatusPill :color="run.status === 'partial' ? 'amber' : 'neutral'">{{ statusText(run.status) }}</StatusPill></td>
            <td>{{ percent(run.metrics?.recall_at_k) }}</td>
            <td class="mono">{{ decimal(run.metrics?.mrr) }}</td>
            <td>{{ percent(run.metrics?.refusal_accuracy, '未评估') }}</td>
            <td>{{ percent(run.metrics?.keyword_coverage, '未评估') }}</td>
            <td>{{ run.metrics?.failures ?? '—' }}</td>
            <td><button class="btn" @click="showRun(run)">查看运行</button></td>
          </tr>
        </VTable>
      </VPanel>
    </div>
  </template>
</template>
