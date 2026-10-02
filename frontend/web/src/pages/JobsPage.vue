<!-- 作业中心（对应 V2 admin-workflows.js 的 jobPage） -->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { listJobs } from '../api/endpoints'
import type { Job } from '../api/types'
import DataPage from '../components/DataPage.vue'
import DataState from '../components/DataState.vue'
import Icon from '../components/Icon.vue'
import SimpleModal from '../components/SimpleModal.vue'
import StatusPill from '../components/StatusPill.vue'
import VPanel from '../components/VPanel.vue'
import VStat from '../components/VStat.vue'
import { actionBusy } from '../composables/useAdminActions'
import { reportDataTime } from '../composables/useDataTime'
import { openModal } from '../composables/useModal'
import { useUrlState } from '../composables/useUrlState'
import JobDetailModal from './workflows/JobDetailModal.vue'
import { jobColor, jobGroup, jobLabels, listStamp } from './workflows/shared'

const client = useQueryClient()
const filter = useUrlState('status', 'all')
const group = useUrlState('group', 'all')
const name = useUrlState('name', '')

const running = (rows?: Job[]) => !!rows?.some((r) => r.status === 'running')
const jobs = useQuery({
  queryKey: ['jobs'],
  queryFn: listJobs,
  refetchInterval: (q) => (running(q.state.data?.jobs) && !actionBusy.value ? 3000 : false),
})
watch(jobs.dataUpdatedAt, reportDataTime, { immediate: true })
// 运行中的作业结束后，业务数据可能已变化，统一刷新
watch(
  () => jobs.data.value?.jobs,
  (now, before) => {
    if (!before || !now) return
    const ended = before.some((r) => r.status === 'running' && now.find((n) => n.name === r.name)?.status !== 'running')
    if (ended) client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'jobs' })
  },
)

const rows = computed(() => jobs.data.value?.jobs)
const count = (s: string) => rows.value?.filter((r) => r.status === s).length
const shown = computed(() =>
  (rows.value ?? []).filter(
    (r) =>
      (filter.value === 'all' || r.status === filter.value) &&
      (group.value === 'all' || jobGroup(r.name) === group.value) &&
      `${r.name} ${r.title}`.toLowerCase().includes(name.value.toLowerCase()),
  ),
)
const setFilter = (key: string) => (filter.value = key)
const setGroup = (v: string) => (group.value = v)
const setName = (v: string) => (name.value = v)

const openJob = (jobName: string) => openModal({ title: '作业状态与日志', view: JobDetailModal, props: { name: jobName }, cls: 'workflow-dialog' })
const guideHtml =
  '<ol class="workflow-guide"><li><strong>先检查执行条件</strong><p>选定登记作业，核对数据库、模型、材料和运行资源。</p></li><li><strong>确认后启动，再追踪状态</strong><p>登记作业均可在详情核对后启动；按后台返回的状态和日志判断进展，同一作业运行中不能重复启动。</p></li><li><strong>回到业务页核对结果</strong><p>进程完成后检查真实库存或报告。失败时保留已完成步骤，检查依赖后再决定是否重跑。</p></li></ol><div class="notice section-gap">本页复用现有白名单作业接口，支持核对后启动与停止，运行中轮询状态和日志。样例详情可手动切换状态。</div>'
const openGuide = () => openModal({ title: '作业运行流程', view: SimpleModal, props: { html: guideHtml } })
</script>

<template>
  <DataPage page="jobs">
    <template #actions>
      <button class="btn soft" @click="openGuide">查看运行流程</button>
    </template>

    <div class="stat-strip data-metrics">
      <VStat label="登记作业" :value="rows?.length" unit="项" foot="当前后端登记的作业" />
      <VStat label="运行中" :value="count('running')" unit="项" foot="本次服务运行状态" />
      <VStat label="进程执行完成" :value="count('ok')" unit="项" foot="仍需核对业务报告" />
      <VStat label="进程执行失败" :value="count('failed')" unit="项" foot="按日志检查执行条件" />
    </div>
    <div class="workflow-scope">
      <span><Icon name="clock" />运行状态属于本次服务；既有日志时间不代表本次执行完成。</span>
      <span>执行完成后，回业务页核对结果</span>
    </div>

    <DataState v-if="!jobs.data.value" :loading="jobs.isPending.value" :error="jobs.error.value" />
    <VPanel v-else title="登记作业与本次状态">
      <template #extra><StatusPill color="neutral">核对后操作</StatusPill></template>
      <div class="panel-toolbar data-toolbar">
        <div class="data-filters">
          <button
            v-for="(label, key) in { all: '全部', ...jobLabels }"
            :key="key"
            class="filter-chip"
            :class="{ active: filter === key }"
            :aria-pressed="filter === key"
            @click="setFilter(String(key))"
          >
            {{ label }}
          </button>
        </div>
        <div class="data-table-tools">
          <select id="wf-job-group" aria-label="作业分组" :value="group" @change="setGroup(($event.target as HTMLSelectElement).value)">
            <option v-for="key in ['all', '知识处理', '训练与评测', '归类与服务']" :key="key" :value="key">{{ key === 'all' ? '全部分组' : key }}</option>
          </select>
          <label class="search"
            ><input id="wf-job-query" aria-label="筛选登记作业" placeholder="筛选名称" :value="name" @input="setName(($event.target as HTMLInputElement).value)"
          /></label>
        </div>
      </div>
      <div class="table-wrap">
        <table class="workflow-job-table">
          <thead>
            <tr>
              <th v-for="h in ['作业名称', '执行条件', '本次状态', '本次执行时间', '操作']" :key="h">{{ h }}</th>
            </tr>
          </thead>
          <tbody id="wf-job-rows">
            <tr v-for="row in shown" :key="row.name">
              <td class="data-content-cell">
                <strong>{{ row.title }}</strong><span class="table-sub">{{ row.name }} · {{ jobGroup(row.name) }}</span>
              </td>
              <td class="workflow-needs">
                {{ row.needs }}<span v-if="row.heavy" class="table-sub">重任务 · 需预留时间与资源</span>
              </td>
              <td>
                <StatusPill :color="jobColor(row.status)">{{ jobLabels[row.status] || row.status || '未知' }}</StatusPill
                ><span v-if="row.status === 'idle' && row.log_mtime" class="table-sub">有既存日志</span>
              </td>
              <td class="data-time-cell">
                <span v-if="row.started_at">开始 {{ listStamp(row.started_at) }}</span>
                <span v-if="row.finished_at">结束 {{ listStamp(row.finished_at) }}</span>
                <span v-if="!row.started_at && !row.finished_at">—</span>
              </td>
              <td>
                <button class="table-actions" @click="openJob(row.name)">详情与运行 <Icon name="arrow" /></button>
              </td>
            </tr>
            <tr v-if="!shown.length">
              <td colspan="5"><div class="empty">当前筛选下没有作业</div></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="data-table-footer">
        <span>状态与日志来自后台；打开详情核对后启动或停止</span>
        <span>不根据耗时推测进度</span>
      </div>
    </VPanel>
  </DataPage>
</template>
