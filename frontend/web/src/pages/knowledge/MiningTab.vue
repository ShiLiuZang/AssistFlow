<!-- 候选问答（对应 V2 miningPage） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { listStaging } from '../../api/endpoints'
import type { StagingStatus } from '../../api/types'
import DataState from '../../components/DataState.vue'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import VStat from '../../components/VStat.vue'
import { openModal } from '../../composables/useModal'
import { useUrlState } from '../../composables/useUrlState'
import CandidateDetailModal from './CandidateDetailModal.vue'
import { num } from './state'

const labels: Record<StagingStatus, string> = {
  kept: '待审核',
  extracted: '已抽取',
  discarded: '去重已丢弃',
  approved: '已采纳',
  rejected: '人工已弃用',
}
const candidate = useUrlState('stage', 'kept')
const { data, error, isPending } = useQuery({ queryKey: ['kb', 'staging'], queryFn: () => listStaging(30) })
const counts = computed<Record<string, number>>(() => data.value?.stats?.counts ?? {})
const rows = computed(() => data.value?.rows?.[candidate.value as StagingStatus] ?? [])
const show = (id: number) => openModal({ title: '候选问答详情', view: CandidateDetailModal, props: { id }, cls: 'knowledge-dialog' })
</script>

<template>
  <DataState :loading="isPending" :error="error" />
  <template v-if="data">
    <div class="stat-strip data-metrics">
      <VStat label="待人工审核" :value="counts.kept" unit="条" foot="去重后保留的候选" />
      <VStat label="已采纳入库" :value="counts.approved" unit="条" foot="以全量统计为准" />
      <VStat label="人工已弃用" :value="counts.rejected" unit="条" foot="与去重丢弃分别计数" />
      <VStat label="抽取批次" :value="data.stats?.batches" unit="批" foot="保留来源和批次" />
    </div>
    <VPanel title="候选问答">
      <template #extra><StatusPill color="neutral">独立审核队列</StatusPill></template>
      <div class="panel-toolbar data-filters">
        <button
          v-for="(label, key) in labels"
          :key="key"
          class="filter-chip"
          :class="{ active: candidate === key }"
          :aria-pressed="candidate === key"
          @click="candidate = key"
        >
          {{ label }} <span>{{ num(counts[key]) }}</span>
        </button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th v-for="h in ['问题与答案摘要', '材料来源', '批次', '状态', '操作']" :key="h">{{ h }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td class="data-content-cell">
                <strong>{{ row.question }}</strong>
                <p class="data-answer-preview">{{ row.answer }}</p>
              </td>
              <td class="mono">{{ row.source_ref || '未标注材料' }}</td>
              <td>{{ row.batch_no || '—' }}</td>
              <td><StatusPill :color="candidate === 'kept' ? 'amber' : 'neutral'">{{ labels[candidate as StagingStatus] }}</StatusPill></td>
              <td><button class="table-actions" @click="show(row.id)">查看</button></td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="5"><div class="empty">没有符合条件的记录</div></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="data-table-footer">
        <span
          >当前状态全量 {{ num(counts[candidate]) }} 条 · 本次展示 {{ rows.length }} 条<br />每种状态最多读取 {{ data.limit || 30 }} 条；查看详情可核对完整答案与当前材料。</span
        >
        <StatusPill color="neutral">核对后采纳或弃用</StatusPill>
      </p>
    </VPanel>
  </template>
</template>
