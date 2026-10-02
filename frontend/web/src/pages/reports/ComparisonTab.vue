<!-- 检索与生成评估：策略检索对照 + 生成与拒答 + 策略汇总 -->
<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import type { RagReport, StrategySummary } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VTable from '../../components/VTable.vue'
import { decimal, finite, name, percent, reportUI } from './state'

const props = defineProps<{ report: RagReport; summaries: [string, StrategySummary][] }>()
defineEmits<{ strategy: [key: string] }>()

const choices = computed(() => [
  ['mrr', 'MRR'],
  ['recall_at_k', `Recall@${props.report.k ?? 'K'}`],
])
watchEffect(() => {
  if (!props.report.summary?.[reportUI.generationStrategy]) reportUI.generationStrategy = props.summaries[0]?.[0] ?? ''
})
const selected = computed(() => props.report.summary?.[reportUI.generationStrategy] ?? {})
const metricOf = (s: StrategySummary) => (reportUI.metric === 'recall_at_k' ? s.recall_at_k : s.mrr)
const width = (v: unknown) => `${Math.max(0, Math.min(100, (v as number) * 100))}%`
const setMetric = (key: string) => (reportUI.metric = key)
const setStrategy = (v: string) => (reportUI.generationStrategy = v)
</script>

<template>
  <div class="report-two-col">
    <VPanel title="策略检索对照">
      <template #extra><StatusPill color="neutral">已保存报告</StatusPill></template>
      <div class="panel-toolbar">
        <button v-for="[key, label] in choices" :key="key" class="filter-chip" :class="{ active: reportUI.metric === key }" :aria-pressed="reportUI.metric === key" @click="setMetric(key)">
          {{ label }}
        </button>
      </div>
      <div class="bar-chart" aria-label="策略检索指标">
        <div v-for="[strategy, s] in summaries" :key="strategy" class="bar-row">
          <span>{{ name(strategy) }}</span>
          <div class="bar-track"><span v-if="finite(metricOf(s))" :style="{ width: width(metricOf(s)) }"></span></div>
          <b>{{ decimal(metricOf(s)) }}</b>
        </div>
        <div class="chart-foot">范围 0–1 · 未提供的指标显示 —</div>
      </div>
    </VPanel>
    <VPanel title="生成与拒答">
      <div class="panel-pad">
        <label class="report-select"
          >查看策略<select id="report-generation-strategy" aria-label="生成指标策略" :value="reportUI.generationStrategy" @change="setStrategy(($event.target as HTMLSelectElement).value)">
            <option v-for="[key] in summaries" :key="key" :value="key">{{ name(key) }}</option>
          </select></label
        >
        <div class="score-row"><span>拒答准确率</span><strong>{{ percent(selected.refusal_accuracy, '未评估') }}</strong></div>
        <div class="score-row"><span>关键词覆盖率</span><strong>{{ percent(selected.keyword_coverage, '未评估') }}</strong></div>
        <p class="field-hint">拒答准确率包含可答与应拒两类题。关键词覆盖仅检查预期词是否出现，不代表忠实度或确认编造率。</p>
        <p v-if="report.generation === false" class="field-hint section-gap">本报告仅评估检索，未运行答案生成。</p>
      </div>
    </VPanel>
  </div>
  <VPanel title="策略汇总">
    <VTable :heads="['检索策略', `Recall@${report.k ?? 'K'}`, 'MRR', '可答 / 总题数', '拒答准确率', '关键词覆盖率', '调用失败', '操作']" :empty="!summaries.length">
      <tr v-for="[strategy, s] in summaries" :key="strategy">
        <td><strong>{{ name(strategy) }}</strong><span class="table-sub mono">{{ strategy }}</span></td>
        <td>{{ percent(s.recall_at_k) }}</td>
        <td class="mono">{{ decimal(s.mrr) }}</td>
        <td>{{ s.answerable_cases ?? '—' }} / {{ s.cases ?? '—' }}</td>
        <td>{{ percent(s.refusal_accuracy, '未评估') }}</td>
        <td>{{ percent(s.keyword_coverage, '未评估') }}</td>
        <td>
          <StatusPill v-if="s.failures" color="red">{{ s.failures }} 条</StatusPill><template v-else>{{ s.failures ?? '—' }}</template>
        </td>
        <td><button class="btn" @click="$emit('strategy', strategy)">逐题查看</button></td>
      </tr>
    </VTable>
    <p class="data-table-footer">召回率与 MRR 按有标准证据组的可答题平均；库外应拒题不进入召回分母。</p>
  </VPanel>
</template>
