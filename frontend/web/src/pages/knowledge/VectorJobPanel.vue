<!-- 向量补齐作业（对应 V2 vectorJobView / prepareVector / startVector） -->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { request } from '../../api/client'
import type { Job, KbOverview } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import VPanel from '../../components/VPanel.vue'
import { actionBusy } from '../../composables/useAdminActions'
import { openModal } from '../../composables/useModal'
import VectorConfirmModal from './VectorConfirmModal.vue'
import { kb, num, stamp, vectorLabels } from './state'

const props = defineProps<{ data: KbOverview }>()
const router = useRouter()
const client = useQueryClient()
const jobQuery = useQuery({
  queryKey: ['job', 'kb-vectorize'],
  queryFn: () => request<Job>('/api/jobs/kb-vectorize'),
  refetchInterval: (q) => (q.state.data?.status === 'running' ? 3000 : false),
})
const job = computed(() => jobQuery.data.value)
// 运行中 → 结束：重新读取库存，提示核对
watch(
  () => job.value?.status,
  (now, before) => {
    if (before === 'running' && now && now !== 'running') {
      kb.vectorNotice = '作业已返回结束状态，库存已重新读取；请核对剩余原文和日志。'
      client.invalidateQueries({ queryKey: ['kb'] })
    }
    if (now && now !== 'idle' && kb.vectorStartUnknown) {
      kb.vectorStartUnknown = false
      kb.vectorNotice = '已查询到真实作业状态，请结合库存和日志核对。'
    }
  },
)
const busy = computed(() => kb.ingestBusy || kb.vectorChecking || kb.vectorStarting || actionBusy.value)
const s = computed(() => props.data.chunks)
const canPrepare = computed(
  () =>
    !busy.value &&
    !jobQuery.isFetching.value &&
    !props.data.db_error &&
    Number.isInteger(s.value.pending) &&
    (s.value.pending ?? 0) > 0 &&
    props.data.milvus?.online === true &&
    job.value?.name === 'kb-vectorize' &&
    Object.hasOwn(vectorLabels, job.value.status) &&
    job.value.status !== 'running',
)
const note = computed(() => {
  const j = job.value
  if (jobQuery.error.value) return '作业状态读取失败，请重新查询；不能据此判断任务已停止。'
  if (!j) return '正在读取向量化作业状态。'
  if (j.status === 'running') return '作业正在运行。仅查询真实状态，不按耗时推测进度。'
  if (j.status === 'failed') return '进程失败，可能已完成部分批次。按当前库存核对剩余原文，修复依赖后再补齐，无需重录。'
  if (j.status === 'ok') return '进程已执行完成。请核对当前待向量化数量与向量库记录；完成状态不代替检索质量验收。'
  if (j.status === 'stopped') return '作业已停止，已完成批次仍需按库存核对。'
  if (j.status === 'idle' && j.log_mtime) return '本次服务没有运行记录，存在既有日志。服务重启会清空运行状态，旧日志不代表本次结果。'
  if (s.value.pending === 0) return '当前没有待向量化原文，无需启动作业。'
  return '处理全库待向量化原文，需要数据库、嵌入服务与向量库。'
})
const pillText = computed(() =>
  job.value ? vectorLabels[job.value.status] || '状态未知' : jobQuery.error.value ? '状态读取失败' : '正在读取',
)
const pillColor = computed(() => (job.value?.status === 'failed' ? 'red' : job.value?.status === 'running' ? 'amber' : 'neutral'))

function prepare() {
  if (!canPrepare.value) return
  openModal({ title: '核对向量补齐', view: VectorConfirmModal, cls: 'knowledge-dialog' })
}
</script>

<template>
  <VPanel title="向量补齐作业">
    <div class="panel-pad">
      <div class="data-vector-top">
        <div>
          <p class="mono muted">kb-vectorize</p>
          <p class="data-vector-note">{{ note }}</p>
        </div>
        <StatusPill :color="pillColor">{{ pillText }}</StatusPill>
      </div>
      <div v-if="kb.vectorNotice" class="notice amber" role="status">{{ kb.vectorNotice }}</div>
      <dl class="data-record-fields">
        <div><dt>全库待向量化</dt><dd>{{ num(s.pending) }} 块</dd></div>
        <div><dt>开始时间</dt><dd>{{ stamp(job?.started_at) }}</dd></div>
        <div><dt>结束时间</dt><dd>{{ stamp(job?.finished_at) }}</dd></div>
        <div><dt>退出码</dt><dd>{{ num(job?.returncode) }}</dd></div>
        <div><dt>日志更新时间</dt><dd>{{ stamp(job?.log_mtime) }}</dd></div>
      </dl>
      <div class="form-actions">
        <button class="btn primary" :disabled="!canPrepare" @click="prepare">
          {{ kb.vectorStarting ? '正在提交启动…' : kb.vectorChecking ? '正在核对…' : '重跑向量化' }}
        </button>
        <button class="btn soft" :disabled="busy || jobQuery.isFetching.value" @click="jobQuery.refetch()">
          {{ jobQuery.isFetching.value ? '正在查询…' : '刷新作业状态' }}
        </button>
        <button class="btn" @click="router.push('/jobs')">打开作业中心</button>
      </div>
      <details v-if="job" class="data-vector-log">
        <summary>查看日志末尾 · 最多 400 行</summary>
        <pre tabindex="0" aria-label="向量补齐作业日志">{{ job.log || '暂无可读取的日志。' }}</pre>
      </details>
      <p class="field-hint section-gap">此作业处理启动时全库 pending 原文，包含历史待补块；不会只处理上一次录入的记录。启动需要人工确认，会调用嵌入服务。</p>
    </div>
  </VPanel>
</template>
