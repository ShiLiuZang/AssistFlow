<!-- 逐题评估结果：按策略、结果和题目筛选（策略与结果写入 URL） -->
<script setup lang="ts">
import { computed } from 'vue'
import type { RagReport } from '../../api/types'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { openModal } from '../../composables/useModal'
import { useUrlState } from '../../composables/useUrlState'
import ResultDetailModal from './ResultDetailModal.vue'
import { decimal, judge, name, outcome, percent, reportUI } from './state'

const props = defineProps<{ report: RagReport }>()
const strategy = useUrlState('strategy', 'all')
const outcomeFilter = useUrlState('outcome', 'all')
const outcomes = [
  ['all', '全部结果'],
  ['error', '调用失败'],
  ['incorrect', '拒答判断不符'],
  ['correct', '拒答判断符合'],
  ['retrieval', '仅检索'],
  ['unknown', '生成未评估'],
]
const details = computed(() => props.report.details ?? [])
const rows = computed(() =>
  details.value.filter(
    (row) =>
      (strategy.value === 'all' || row.strategy === strategy.value) &&
      (outcomeFilter.value === 'all' || outcome(row, props.report)[0] === outcomeFilter.value) &&
      `${row.query || ''} ${row.id || ''}`.toLowerCase().includes(reportUI.query.toLowerCase()),
  ),
)
const setStrategy = (v: string) => (strategy.value = v)
const setOutcome = (v: string) => (outcomeFilter.value = v)
const show = (index: number) => {
  const row = rows.value[index]
  openModal({
    title: '逐题评估依据',
    view: ResultDetailModal,
    props: { row, item: props.report.dataset?.find((c) => c.id === row.id), generation: props.report.generation, outcome: outcome(row, props.report) },
    cls: 'report-dialog',
  })
}
</script>

<template>
  <VPanel title="逐题评估结果">
    <div class="panel-toolbar data-toolbar">
      <div class="data-table-tools">
        <select id="report-strategy" aria-label="筛选评估策略" :value="strategy" @change="setStrategy(($event.target as HTMLSelectElement).value)">
          <option value="all">全部策略</option>
          <option v-for="key in Object.keys(report.summary ?? {})" :key="key" :value="key">{{ name(key) }}</option>
        </select>
        <select id="report-outcome" aria-label="筛选评估结果" :value="outcomeFilter" @change="setOutcome(($event.target as HTMLSelectElement).value)">
          <option v-for="[key, label] in outcomes" :key="key" :value="key">{{ label }}</option>
        </select>
      </div>
      <label class="search"><Icon name="search" /><input id="report-query" v-model="reportUI.query" aria-label="筛选报告内题目" placeholder="筛选本报告题目" /></label>
    </div>
    <div class="table-wrap">
      <table class="report-results-table">
        <thead>
          <tr>
            <th v-for="h in ['问题', '策略', '召回 / 倒数排名', '标准判断', '执行与生成结果', '操作']" :key="h">{{ h }}</th>
          </tr>
        </thead>
        <tbody id="report-result-rows">
          <tr v-for="(row, index) in rows" :key="`${row.strategy}-${row.id}`">
            <td class="data-content-cell"><strong>{{ row.query || '未标注问题' }}</strong><span class="table-sub mono">{{ row.id }}</span></td>
            <td>{{ name(row.strategy) }}</td>
            <td>{{ row.error ? '—' : percent(row.recall) }}<span class="table-sub">RR {{ row.error ? '—' : decimal(row.rr) }}</span></td>
            <td>{{ judge(row.should_refuse) }}</td>
            <td>
              <StatusPill :color="outcome(row, report)[2]">{{ outcome(row, report)[1] }}</StatusPill
              ><span v-if="row.error" class="table-sub mono">{{ row.error }}</span>
            </td>
            <td><button class="btn" @click="show(index)">查看依据</button></td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="6"><div class="empty">本报告内没有符合条件的结果</div></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="data-table-footer">
      <span id="report-result-count">当前匹配 {{ rows.length }} / {{ details.length }} 条</span><span>每条记录对应一个题目与一种策略；不是累计问题台账。</span>
    </p>
  </VPanel>
</template>
