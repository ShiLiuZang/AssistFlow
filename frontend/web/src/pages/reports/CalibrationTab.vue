<!-- 置信度校准：阈值扫描与两类题目的分数分布（只读，不修改配置） -->
<script setup lang="ts">
import { computed } from 'vue'
import type { CalibrationBlock } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VStat from '../../components/VStat.vue'
import VTable from '../../components/VTable.vue'
import { openModal } from '../../composables/useModal'
import CalibrationModal from './CalibrationModal.vue'
import ReportMeta from './ReportMeta.vue'
import { decimal, finite, percent } from './state'

const props = defineProps<{ data: CalibrationBlock }>()
const current = computed(() => props.data.in_use)
const recommended = computed(() => props.data.recommended?.threshold)
const sync = computed(() => (props.data.in_sync === true ? '一致' : props.data.in_sync === false ? '不一致' : '未核对'))
const fields = ['min', 'p25', 'p50', 'p75', 'max'] as const
const dist = (key: 'answerable' | 'absent') => props.data.distribution?.[key] ?? {}
const showSamples = () => openModal({ title: '独立校准样本', view: CalibrationModal, props: { scored: props.data.scored ?? [] } })
</script>

<template>
  <ReportMeta
    :items="[
      ['报告生成', data.created_at?.replace('T', ' ')],
      ['校准数据集', data.dataset_version],
    ]"
  />
  <div class="stat-strip data-metrics">
    <VStat label="当前运行阈值" :value="finite(current) ? current.toFixed(2) : null" foot="当前服务配置" />
    <VStat label="报告推荐阈值" :value="finite(recommended) ? recommended.toFixed(2) : null" foot="独立校准集扫描结果" />
    <VStat label="扫描候选" :value="Array.isArray(data.scan) ? data.scan.length : null" unit="个" foot="报告保存的候选值" />
    <VStat label="配置核对" :value="sync" foot="查看报告不会修改配置" />
  </div>
  <div class="notice report-note" :class="{ amber: data.in_sync === false }" :role="data.in_sync === false ? 'alert' : undefined">
    可答题放行率衡量可答题达到阈值的比例；应拒题放行率衡量应拒题达到阈值的比例。放行不等于回答正确。推荐值与当前配置分别显示，页面不应用阈值。
  </div>
  <VPanel title="证据置信度阈值扫描">
    <template #extra><button class="btn" @click="showSamples">查看校准样本</button></template>
    <VTable :heads="['候选阈值', '可答题放行率', '应拒题放行率', 'Youden J', '说明']" :empty="!data.scan?.length">
      <tr v-for="row in data.scan ?? []" :key="row.threshold" :class="{ 'report-recommended': row.threshold === recommended }">
        <td class="mono">{{ finite(row.threshold) ? row.threshold.toFixed(2) : '—' }}</td>
        <td>{{ percent(row.pass_rate) }}</td>
        <td>{{ percent(row.leak_rate) }}</td>
        <td class="mono">{{ decimal(row.youden_j) }}</td>
        <td><StatusPill v-if="row.threshold === recommended">报告推荐</StatusPill><StatusPill v-if="row.threshold === current" color="neutral">当前值</StatusPill></td>
      </tr>
    </VTable>
    <p class="data-table-footer">Youden J = 可答题放行率 − 应拒题放行率；此处是 RAG 证据阈值，分类器标签阈值另行管理。</p>
  </VPanel>
  <div class="section-gap">
    <VPanel title="两类题目的分数分布">
      <VTable :heads="['样本类别', '数量', '最小值', 'P25', 'P50', 'P75', '最大值']">
        <tr v-for="key in ['answerable', 'absent'] as const" :key="key">
          <td>{{ key === 'answerable' ? '可回答题' : '应拒答题' }}</td>
          <td>{{ dist(key).n ?? '—' }}</td>
          <td v-for="f in fields" :key="f" class="mono">{{ decimal(dist(key)[f]) }}</td>
        </tr>
      </VTable>
    </VPanel>
  </div>
</template>
