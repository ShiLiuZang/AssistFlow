<!-- 作业状态与日志（对应 V2 jobBody / jobFooter） -->
<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { getJob } from '../../api/endpoints'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import { actionBusy, jobAction } from '../../composables/useAdminActions'
import { closeModal, openModal } from '../../composables/useModal'
import JobDetailModal from './JobDetailModal.vue'
import { jobColor, jobLabels, jobResultPage, stamp } from './shared'

const props = defineProps<{ name: string }>()
const router = useRouter()
const { data: row, error, isPending, isFetching, refetch } = useQuery({
  queryKey: ['jobs', 'item', props.name],
  queryFn: () => getJob(props.name),
  gcTime: 0,
  refetchInterval: (q) => (q.state.data?.status === 'running' && !actionBusy.value ? 3000 : false),
})

const reopen = () => openModal({ title: '作业状态与日志', view: JobDetailModal, props: { name: props.name }, cls: 'workflow-dialog' })
const toggle = () => jobAction(props.name, row.value?.status === 'running', reopen)
function toResult() {
  closeModal()
  router.push(jobResultPage(props.name))
}
</script>

<template>
  <div class="modal-body">
    <div v-if="isPending" class="empty" role="status">正在读取作业状态与日志…</div>
    <div v-else-if="error" class="notice" role="alert">{{ error.message }}</div>
    <template v-else-if="row">
      <div class="workflow-detail-top">
        <div>
          <span class="mono muted">{{ row.name }}</span>
          <h3>{{ row.title }}</h3>
        </div>
        <StatusPill :color="jobColor(row.status)">{{ jobLabels[row.status] || row.status || '未知' }}</StatusPill>
      </div>
      <div class="workflow-job-detail">
        <section>
          <h3>执行条件与本次状态</h3>
          <p class="muted section-gap">{{ row.needs }}</p>
          <p v-if="row.heavy" class="small section-gap">重任务，需预留时间与运行资源。</p>
          <dl class="workflow-meta">
            <dt>开始时间</dt>
            <dd>{{ stamp(row.started_at) }}</dd>
            <dt>结束时间</dt>
            <dd>{{ stamp(row.finished_at) }}</dd>
            <dt>进程 ID</dt>
            <dd>{{ row.pid ?? '—' }}</dd>
            <dt>退出码</dt>
            <dd>{{ row.returncode ?? '—' }}</dd>
            <dt>既有日志更新</dt>
            <dd>{{ stamp(row.log_mtime) }}</dd>
          </dl>
          <div v-if="row.status === 'idle' && row.log_mtime" class="notice section-gap">本次服务尚未运行此作业，但已有日志文件。日志时间不用于推断本次执行结果。</div>
          <div v-else-if="row.status === 'ok'" class="notice section-gap">进程已执行完成。请打开业务页，核对库存或报告是否符合预期。</div>
          <div v-else-if="row.status === 'failed'" class="notice section-gap">进程执行失败。已完成的业务步骤需单独核对，修复依赖后再决定是否重跑。</div>
          <div v-else-if="row.status === 'running'" class="notice section-gap">当前正在运行；后台未提供进度比例，请按日志确认实际执行情况。</div>
          <p class="field-hint section-gap">启动和停止需单独核对；失败或停止可能保留部分产物，回结果页核对后再重跑。</p>
        </section>
        <section>
          <div class="workflow-section-title">
            <h3>日志末尾</h3>
            <button class="text-button" :disabled="isFetching" @click="refetch()">刷新日志 <Icon name="clock" /></button>
          </div>
          <pre class="workflow-log" tabindex="0" aria-label="作业日志">{{ row.log || '暂无可读取的日志。' }}</pre>
          <p class="field-hint">日志末尾最多 400 行；旧日志与本次运行状态分别判断。</p>
        </section>
      </div>
    </template>
  </div>
  <div class="modal-foot">
    <button class="btn" @click="closeModal">关闭</button>
    <button v-if="error" class="btn primary" @click="refetch()">重新读取</button>
    <template v-else-if="row">
      <button class="btn soft" @click="toResult">打开结果页</button>
      <button v-if="['idle', 'running', 'ok', 'failed', 'stopped'].includes(row.status)" class="btn primary" :disabled="actionBusy" @click="toggle">
        {{ row.status === 'running' ? '核对并停止' : '核对并启动' }}
      </button>
    </template>
  </div>
</template>
