<!-- 观测与成本：模型用量与费用、固定集复评趋势、证据置信度阈值校准。缺失项显示原因，不补零 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getObservability } from '../api/endpoints'
import BarList from '../components/BarList.vue'
import PageHeader from '../components/PageHeader.vue'
import Panel from '../components/Panel.vue'
import Pill from '../components/Pill.vue'
import StatCard from '../components/StatCard.vue'
import StateBlock from '../components/StateBlock.vue'
import { dateTime, fixed, isNum, num, pct, DASH } from '../utils/format'

const { data, error, isPending, isFetching, refetch } = useQuery({
  queryKey: ['observability'],
  queryFn: getObservability,
})

const cost = computed(() => data.value?.cost)
const totalTokens = computed(() => {
  const s = cost.value?.summary
  return s ? s.known_input_tokens + s.known_output_tokens : null
})
// 费用按币种分别汇总，不同币种不相加
const costByCurrency = computed(() => {
  const totals: Record<string, number> = {}
  for (const row of cost.value?.rows ?? []) {
    for (const [currency, amount] of Object.entries(row.priced_subtotals)) {
      totals[currency] = (totals[currency] ?? 0) + Number(amount)
    }
  }
  return Object.entries(totals)
})
const intentBars = computed(() =>
  (cost.value?.rows ?? []).map((r) => ({ label: r.intent, value: r.input_tokens + r.output_tokens })),
)

const trend = computed(() => data.value?.trend)
const metricLabels: Record<string, string> = {
  recall_at_k: '召回@K',
  mrr: 'MRR',
  refusal_accuracy: '拒答准确率',
  faithfulness: '忠实度',
}

const calibration = computed(() => data.value?.calibration)
const distRows = [
  ['answerable', '应可回答'],
  ['absent', '知识库没有'],
] as const
const statusTone = (s?: string) => (s === 'ok' ? 'green' : s === 'error' ? 'red' : 'neutral')
const statusText = (s?: string) => (s === 'ok' ? '已就绪' : s === 'error' ? '读取失败' : '未就绪')
</script>

<template>
  <PageHeader eyebrow="OBSERVABILITY" title="观测与成本" desc="核对调用消耗、可比较评测与证据阈值。本页只读。">
    <button class="btn" type="button" :disabled="isFetching" @click="refetch()">{{ isFetching ? '刷新中…' : '刷新读数' }}</button>
  </PageHeader>

  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />

  <template v-if="data && cost && trend && calibration">
    <!-- 成本 -->
    <Panel title="模型用量与成本">
      <template #extra>
        <Pill :tone="statusTone(cost.status)">{{ statusText(cost.status) }}</Pill>
        <span v-if="cost.meta" class="small muted">生成于 {{ dateTime(cost.meta.generated_at) }}</span>
      </template>
      <p v-if="cost.status !== 'ok'" class="muted">{{ cost.hint }}</p>
      <template v-else-if="cost.summary">
        <div class="stat-strip flat">
          <StatCard label="Token 总数" :value="totalTokens" foot="已知输入 + 输出" />
          <StatCard label="输入 Token" :value="cost.summary.known_input_tokens" />
          <StatCard label="输出 Token" :value="cost.summary.known_output_tokens" />
          <StatCard label="模型调用" :value="cost.summary.generations" unit="次" :foot="`${cost.summary.requests} 个请求`" />
          <StatCard
            v-for="[currency, amount] in costByCurrency"
            :key="currency"
            :label="`估算费用（${currency}）`"
            :value="amount.toFixed(4)"
            foot="仅按输入输出计价"
          />
        </div>
        <p v-if="cost.summary.unknown_usage || cost.summary.unpriced" class="notice warn">
          有 {{ cost.summary.unknown_usage }} 次调用缺少用量、{{ cost.summary.unpriced }} 次没有价格，费用为不完整估算。
        </p>
        <div class="grid-2">
          <div>
            <h3 class="sub">按意图的 Token 分布</h3>
            <BarList :items="intentBars" />
          </div>
          <div class="table-wrap">
            <table class="data">
              <thead>
                <tr>
                  <th>意图</th>
                  <th class="num">请求</th>
                  <th class="num">调用</th>
                  <th class="num">输入</th>
                  <th class="num">输出</th>
                  <th class="num">P95 耗时</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in cost.rows" :key="r.intent">
                  <td>{{ r.intent }}</td>
                  <td class="num">{{ num(r.requests) }}</td>
                  <td class="num">{{ num(r.generations) }}</td>
                  <td class="num">{{ num(r.input_tokens) }}</td>
                  <td class="num">{{ num(r.output_tokens) }}</td>
                  <td class="num">{{ isNum(r.p95_generation_ms) ? `${Math.round(r.p95_generation_ms)} ms` : DASH }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </Panel>

    <div class="grid-2">
      <!-- 复评趋势 -->
      <Panel title="固定集复评趋势">
        <template #extra><Pill :tone="statusTone(trend.status)">{{ statusText(trend.status) }}</Pill></template>
        <p v-if="trend.status !== 'ok'" class="muted">{{ trend.hint }}</p>
        <template v-else>
          <div class="table-wrap">
            <table class="data">
              <thead>
                <tr>
                  <th>运行</th>
                  <th v-for="m in trend.metric_names" :key="m" class="num">{{ metricLabels[m] ?? m }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="run in trend.runs" :key="run.id">
                  <td class="small">#{{ run.id }} · {{ dateTime(run.created_at) }}</td>
                  <td v-for="m in trend.metric_names" :key="m" class="num">{{ fixed(run.metrics?.[m]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="small muted">
            {{ trend.hint }}<template v-if="trend.omitted_incomparable">已省略 {{ trend.omitted_incomparable }} 次不可比的运行。</template>
          </p>
        </template>
      </Panel>

      <!-- 阈值校准 -->
      <Panel title="证据置信度阈值">
        <template #extra><Pill :tone="statusTone(calibration.status)">{{ statusText(calibration.status) }}</Pill></template>
        <p v-if="calibration.status !== 'ok'" class="muted">{{ calibration.hint }}</p>
        <template v-else-if="calibration.recommended">
          <div class="stat-strip flat">
            <StatCard label="在用阈值" :value="fixed(calibration.in_use, 2)" />
            <StatCard
              label="推荐阈值"
              :value="fixed(calibration.recommended.threshold, 2)"
              :foot="calibration.in_sync ? '与在用一致' : '与在用不一致'"
              :tone="calibration.in_sync ? 'normal' : 'warn'"
            />
            <StatCard label="可答放行率" :value="pct(calibration.recommended.pass_rate)" />
            <StatCard label="无答漏放率" :value="pct(calibration.recommended.leak_rate)" />
          </div>
          <table v-if="calibration.distribution" class="data">
            <thead>
              <tr>
                <th>得分分布</th>
                <th class="num">样本</th>
                <th class="num">P25</th>
                <th class="num">中位数</th>
                <th class="num">P75</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="[key, label] in distRows" :key="key">
                <td>{{ label }}</td>
                <td class="num">{{ calibration.distribution[key].n }}</td>
                <td class="num">{{ fixed(calibration.distribution[key].p25, 2) }}</td>
                <td class="num">{{ fixed(calibration.distribution[key].p50, 2) }}</td>
                <td class="num">{{ fixed(calibration.distribution[key].p75, 2) }}</td>
              </tr>
            </tbody>
          </table>
          <p class="small muted">校准时间 {{ dateTime(calibration.created_at) }}。推荐阈值取放行率与漏放率之差最大处。</p>
        </template>
      </Panel>
    </div>
  </template>
</template>

<style scoped>
.flat {
  border: 0;
  padding: 4px 0;
  margin-bottom: 12px;
}
.sub {
  font-size: 14px;
  margin: 0 0 10px;
}
</style>
