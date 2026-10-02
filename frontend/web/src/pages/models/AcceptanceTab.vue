<!-- 九项验收 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { AcceptanceBlock } from '../../api/types'
import DataState from '../../components/DataState.vue'
import Icon from '../../components/Icon.vue'
import SimpleModal from '../../components/SimpleModal.vue'
import VStat from '../../components/VStat.vue'
import { closeModal, openModal } from '../../composables/useModal'
import GateStatus from '../classification/GateStatus.vue'
import JobButtons from '../classification/JobButtons.vue'
import { trackTime, useClsData, useClsErrors, useClsEval, useOverview } from '../classification/queries'
import { num, serviceDetail } from '../classification/shared'
import GateModal from './GateModal.vue'
import GateNumbers from './GateNumbers.vue'

const emit = defineEmits<{ tab: [key: string] }>()
const router = useRouter()
const v = useOverview()
const data = useClsData()
const evaluation = useClsEval()
const errors = useClsErrors()
trackTime(v)
const d = computed(() => v.data.value)
const blocks = computed(() => d.value?.blocks || [])
const countOf = (s: string) => blocks.value.filter((b) => b.status === s).length

// 验收依据弹窗里的"查看对应报告"
function toReport(key: string) {
  if (key === 'classify') router.push('/topics')
  else if (key === 'golden')
    openModal({
      title: '黄金样例闸 · 数据范围',
      view: SimpleModal,
      props: { html: '<div class="notice report-note amber" role="alert">现有接口提供验收摘要，尚无黄金样例逐条详情查询。未用其他错例代替这项依据。</div>' },
      cls: 'classification-dialog',
    })
  else emit('tab', ['data', 'train', 'export'].includes(key) ? 'data' : key === 'errors' ? 'errors' : 'evaluation')
}
function toJobs() {
  closeModal()
  router.push('/jobs')
}
const showGate = (block: AcceptanceBlock) => openModal({ title: block.title, view: GateModal, props: { block, onReport: toReport, onJobs: toJobs }, cls: 'classification-dialog' })
</script>

<template>
  <DataState v-if="!d" :loading="v.isPending.value" :error="v.error.value" />
  <template v-else>
    <div class="stat-strip data-metrics">
      <VStat label="通过验收" :value="d.passed" :unit="'/ ' + num(d.total)" foot="后端逐项判定" />
      <VStat label="未达标" :value="countOf('fail')" :tone="countOf('fail') ? 'red' : undefined" unit="项" foot="产物存在，但验收条件未满足" />
      <VStat label="未生成" :value="countOf('missing')" unit="项" foot="缺少所需产物或报告" />
      <VStat label="分类服务" :value="d.classifier?.online === true ? '在线' : d.classifier?.online === false ? '离线' : null" :tone="d.classifier?.online === false ? 'red' : undefined" foot="独立健康检查" />
    </div>
    <div class="cls-acceptance-summary" :class="{ 'is-alert': d.all_pass === false }">
      <b>{{ d.all_pass === true ? '全部达标' : d.all_pass === false ? '尚未全部达标' : '验收结论未知' }}</b>
      <span v-if="countOf('fail')">未达标：<strong>{{ blocks.filter(b => b.status === 'fail').map(b => b.title).join('、') }}</strong></span>
      <details>
        <summary>判定与服务说明</summary>
        <p>文件齐全、评测达标与服务在线分别判断。矩阵和错例项达标仅表示报告可读；完整验收需所有项目满足条件。</p>
        <p>服务状态：{{ serviceDetail(d.classifier?.detail) }}</p>
      </details>
    </div>
    <div class="cls-gates">
      <section v-for="b in blocks" :key="b.key" class="panel cls-gate" :class="{ 'is-failed': b.status === 'fail' }">
        <div class="panel-head">
          <h2>
            <span class="mono muted">{{ num(b.no).padStart(2, '0') }}</span> {{ b.title }}
          </h2>
          <GateStatus :status="b.status" />
        </div>
        <div class="panel-pad">
          <GateNumbers :gate="b.key" :data="data.data.value" :evaluation="evaluation.data.value" :errors="errors.data.value" :overview="d" />
          <strong class="cls-gate-headline">{{ b.headline || '尚无结论' }}</strong>
          <p>{{ b.note || '未提供说明' }}</p>
          <JobButtons :jobs="b.jobs" />
          <button class="table-actions" @click="showGate(b)">查看依据 <Icon name="arrow" /></button>
        </div>
      </section>
    </div>
  </template>
</template>
