<!-- RAG 质量（对应 V2 admin-reports.js 的 qualityPage） -->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getRagReport, listEvalCases } from '../api/endpoints'
import DataPage from '../components/DataPage.vue'
import DataState from '../components/DataState.vue'
import VStat from '../components/VStat.vue'
import { dataTime, reportDataTime } from '../composables/useDataTime'
import { useUrlState } from '../composables/useUrlState'
import ComparisonTab from './reports/ComparisonTab.vue'
import DatasetTab from './reports/DatasetTab.vue'
import EvaluationPanel from './reports/EvaluationPanel.vue'
import ReportEmpty from './reports/ReportEmpty.vue'
import ReportMeta from './reports/ReportMeta.vue'
import ResultsTab from './reports/ResultsTab.vue'
import TrialTab from './reports/TrialTab.vue'
import { openGuide } from './reports/guide'
import { decimal, finite, name, reportTime, trial } from './reports/state'

const tabs = [
  ['comparison', '检索与生成评估'],
  ['results', '逐题评估结果'],
  ['dataset', '固定题集'],
  ['trial', '单题体验'],
] as const
const tab = useUrlState('tab', 'comparison')
const strategy = useUrlState('strategy', 'all')
const outcomeFilter = useUrlState('outcome', 'all')
function setTab(key: string) {
  tab.value = key
}

const report = useQuery({ queryKey: ['rag', 'report'], queryFn: getRagReport, enabled: computed(() => tab.value === 'comparison' || tab.value === 'results') })
const cases = useQuery({ queryKey: ['rag', 'cases'], queryFn: listEvalCases, enabled: computed(() => tab.value === 'dataset') })

// 页脚"本次读取"跟随当前子页的数据来源
const shownTime = computed(() =>
  tab.value === 'trial' ? null : tab.value === 'dataset' ? cases.dataUpdatedAt.value : report.dataUpdatedAt.value,
)
watch(shownTime, (t) => (t == null ? undefined : reportDataTime(t)), { immediate: true })
watch(
  () => [tab.value, trial.time] as const,
  ([t, time]) => {
    if (t === 'trial') dataTime.value = time
  },
  { immediate: true },
)

const value = computed(() => report.data.value)
const missing = computed(() => {
  const r = value.value
  if (!r) return null
  if (r.status === 'not_evaluated') return ['尚未评估', '没有已保存的评估报告。固定题集仍可查看；本页不会自动运行评估。']
  if (r.status !== 'evaluated' || !r.summary || !Array.isArray(r.details))
    return ['报告内容待核对', '报告缺少完整的策略汇总或逐题结果，请检查保存报告后重新读取。']
  return null
})
const summaries = computed(() => Object.entries(value.value?.summary ?? {}).filter(([, s]) => s && typeof s === 'object'))
const best = computed(() => summaries.value.filter(([, s]) => finite(s.mrr)).sort((a, b) => (b[1].mrr as number) - (a[1].mrr as number))[0])
const caseCount = computed(() => {
  const values = [...new Set(summaries.value.map(([, s]) => s.cases))]
  return values.length === 1 ? values[0] : null
})
const failures = computed(() => (value.value?.details ?? []).filter((row) => row.error).length)
const info = computed<[string, unknown][]>(() => {
  const r = value.value!
  return [
    ['报告生成', reportTime(r.created_at, '—')],
    ['Top K', r.k],
    ['评估范围', r.generation === true ? '检索 + 生成' : r.generation === false ? '仅检索' : '未标注'],
    ['查询改写', r.rewrite == null ? '未标注' : r.rewrite ? '开启' : '关闭'],
    ['分句检索', r.split == null ? '未标注' : r.split ? '开启' : '关闭'],
  ]
})
function showStrategy(key: string) {
  tab.value = 'results'
  strategy.value = key
  outcomeFilter.value = 'all'
}
</script>

<template>
  <DataPage page="quality">
    <template #actions>
      <button class="btn soft" @click="openGuide">报告运行说明</button>
    </template>

    <nav class="section-tabs" aria-label="RAG 质量子页面">
      <button v-for="[key, label] in tabs" :key="key" :class="{ active: tab === key }" :aria-current="tab === key ? 'page' : 'false'" @click="setTab(key)">
        {{ label }}
      </button>
    </nav>
    <EvaluationPanel v-if="tab !== 'trial'" />

    <TrialTab v-if="tab === 'trial'" />
    <DatasetTab v-else-if="tab === 'dataset'" :query="cases" @try="setTab('trial')" />
    <template v-else>
      <DataState v-if="!value" :loading="report.isPending.value" :error="report.error.value" />
      <ReportEmpty v-else-if="missing" :title="missing[0]" :description="missing[1]" />
      <template v-else>
        <ReportMeta :items="info" />
        <div class="stat-strip data-metrics">
          <VStat label="评估策略" :value="summaries.length" unit="种" foot="本报告策略数" />
          <VStat label="每策略题数" :value="caseCount" unit="题" :foot="caseCount == null ? '各策略题数不同或未标注' : '同一报告内的评估题数'" />
          <VStat label="最佳 MRR" :value="best ? decimal(best[1].mrr) : null" :foot="best ? name(best[0]) : '尚无有效 MRR'" />
          <VStat label="调用失败记录" :value="failures" unit="条" foot="按题目 × 策略分别计数" />
        </div>
        <div v-if="failures" class="notice report-note amber" role="alert">
          存在服务调用失败。失败记录保留在报告汇总中；请结合逐题错误判断读数，不能视为普通零分题目。
        </div>
        <ResultsTab v-if="tab === 'results'" :report="value" />
        <ComparisonTab v-else :report="value" :summaries="summaries" @strategy="showStrategy" />
      </template>
    </template>
  </DataPage>
</template>
