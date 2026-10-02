<!-- 核对全库向量补齐：先重新读取待补数量和作业状态，勾选确认后启动 -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from '../../api/client'
import type { Job, KbOverview } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
import { closeModal, modalState } from '../../composables/useModal'
import { queryClient } from '../../queryClient'
import { kb, vectorLabels } from './state'

const phase = ref<'checking' | 'blocked' | 'confirm' | 'error'>('checking')
const message = ref('')
const latest = ref<KbOverview | null>(null)
const job = ref<Job | null>(null)
const checked = ref(false)

onMounted(async () => {
  kb.vectorChecking = true
  try {
    const [o, j] = await Promise.all([request<KbOverview>('/api/kb/overview'), request<Job>('/api/jobs/kb-vectorize')])
    latest.value = o
    job.value = j
    queryClient.setQueryData(['kb', 'overview'], o)
    queryClient.setQueryData(['job', 'kb-vectorize'], j)
    const ok =
      !o.db_error &&
      Number.isInteger(o.chunks?.pending) &&
      (o.chunks.pending ?? 0) > 0 &&
      o.milvus?.online === true &&
      j.name === 'kb-vectorize' &&
      Object.hasOwn(vectorLabels, j.status) &&
      j.status !== 'running'
    if (!ok) {
      message.value =
        j.status === 'running'
          ? '同一作业已经运行，请查看状态和日志。'
          : o.db_error
            ? '原文库存暂不可读取。'
            : o.chunks?.pending === 0
              ? '当前已没有待向量化原文。'
              : o.milvus?.online !== true
                ? '向量库当前不可用，请恢复服务后重新核对。'
                : '作业状态暂不可确认，请重新查询。'
      phase.value = 'blocked'
      modalState.title = '暂不能启动向量补齐'
      return
    }
    phase.value = 'confirm'
    modalState.title = '核对全库向量补齐'
  } catch (error: any) {
    message.value = error.message
    phase.value = 'error'
    modalState.title = '执行条件暂时无法核对'
  } finally {
    kb.vectorChecking = false
  }
})

async function start() {
  if (!checked.value || phase.value !== 'confirm') return
  kb.vectorStarting = true
  kb.vectorNotice = ''
  kb.vectorStartUnknown = false
  closeModal()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 15000)
  try {
    const response = await fetch('/api/jobs/kb-vectorize', { method: 'POST', signal: controller.signal, headers: { Accept: 'application/json' } })
    if (!response.ok) {
      let detail
      try {
        detail = (await response.json()).detail
      } catch {}
      throw Object.assign(
        new Error(
          response.status === 409
            ? '同一作业已经运行，请查看现有运行状态。'
            : typeof detail === 'string' && response.status < 500
              ? detail
              : `启动请求未返回完整结果（HTTP ${response.status}）。`,
        ),
        { uncertain: response.status >= 500 },
      )
    }
    const j: Job = await response.json()
    if (j.name !== 'kb-vectorize' || !Object.hasOwn(vectorLabels, j.status) || j.status === 'idle') throw new Error('启动结果不完整，请查询真实作业状态。')
    queryClient.setQueryData(['job', 'kb-vectorize'], j)
    kb.vectorNotice = j.status === 'running' ? '已提交启动，正在读取真实作业状态。' : '作业已返回结束状态，请核对库存与日志。'
  } catch (error: any) {
    kb.vectorStartUnknown = error.uncertain !== false
    kb.vectorNotice = error.name === 'AbortError' ? '启动请求超时，尚不能确认是否已启动。请先刷新作业状态，不要直接重复提交。' : error.message
    queryClient.invalidateQueries({ queryKey: ['job', 'kb-vectorize'] })
  } finally {
    clearTimeout(timer)
    kb.vectorStarting = false
    queryClient.invalidateQueries({ queryKey: ['kb'] })
  }
}
</script>

<template>
  <div class="modal-body">
    <div v-if="phase === 'checking'" class="empty" role="status">正在重新读取全库待补数量和作业状态…</div>
    <p v-else-if="phase === 'blocked'">{{ message }}</p>
    <template v-else-if="phase === 'error'">
      <p>{{ message }}</p>
      <p class="field-hint section-gap">尚未发送启动请求，请恢复查询后再核对。</p>
    </template>
    <form v-else-if="latest && job" id="data-vector-form" @submit.prevent="start">
      <div v-if="kb.vectorStartUnknown" class="notice amber">上次启动未收到明确结果。请结合当前运行状态、库存与日志核对，再决定是否重新启动。</div>
      <div class="data-detail-meta">
        <StatusPill color="amber">全库待向量化 {{ latest.chunks.pending }} 块</StatusPill>
        <StatusPill>向量库在线</StatusPill>
        <StatusPill color="neutral">{{ vectorLabels[job.status] }}</StatusPill>
      </div>
      <p>启动现有向量化作业，处理启动时所有 pending 原文，包含历史待补块；实际数量可能随库存变化。会调用嵌入服务，将向量写入向量库，再更新原文状态。</p>
      <p class="field-hint section-gap">失败时保留已完成批次；修复后仅补齐剩余 pending 原文，无需重新录入。运行记录属于当前服务，服务重启后需结合库存与日志核对。</p>
      <label class="data-ingest-check"><input v-model="checked" type="checkbox" required name="checked" />我已核对全库处理范围及执行条件，确认启动向量补齐。</label>
    </form>
  </div>
  <div class="modal-foot">
    <template v-if="phase === 'confirm'">
      <button class="btn" @click="closeModal">继续检查</button>
      <button class="btn primary" type="submit" form="data-vector-form">确认启动向量补齐</button>
    </template>
    <button v-else class="btn" @click="closeModal">知道了</button>
  </div>
</template>
