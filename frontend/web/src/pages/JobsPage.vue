<!-- 作业中心：所有注册的后台作业，按类别分组 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { listJobs } from '../api/endpoints'
import PageHeader from '../components/PageHeader.vue'
import Panel from '../components/Panel.vue'
import JobCard from '../components/JobCard.vue'
import StateBlock from '../components/StateBlock.vue'
import { jobStatus } from '../utils/labels'

const { data, error, isPending, isFetching, refetch } = useQuery({
  queryKey: ['jobs'],
  queryFn: listJobs,
  refetchInterval: (q) => (q.state.data?.jobs.some((j) => j.status === 'running') ? 3000 : false),
})

const groups = computed(() => {
  const jobs = data.value?.jobs ?? []
  return [
    { title: '知识库', items: jobs.filter((j) => j.name.startsWith('kb-')) },
    { title: '分类器训练与验收', items: jobs.filter((j) => j.name.startsWith('finetune-') || j.name === 'classifier-up') },
    { title: '批量归类', items: jobs.filter((j) => j.name.startsWith('classify-')) },
  ].filter((g) => g.items.length)
})

const counts = computed(() => {
  const result: Record<string, number> = {}
  for (const j of data.value?.jobs ?? []) result[j.status] = (result[j.status] ?? 0) + 1
  return result
})
</script>

<template>
  <PageHeader eyebrow="BACKGROUND OPERATIONS" title="作业中心" desc="查看执行条件、运行状态与日志，再回到业务页核对结果。">
    <button class="btn" type="button" :disabled="isFetching" @click="refetch()">刷新读数</button>
  </PageHeader>

  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />

  <template v-if="data">
    <p class="notice">
      共 {{ data.jobs.length }} 个作业：
      <template v-for="(label, key) in jobStatus" :key="key">
        <span v-if="counts[key]">{{ label[0] }} {{ counts[key] }} · </span>
      </template>
      启动前会确认执行条件，关闭页面不会停止作业。
    </p>
    <Panel v-for="g in groups" :key="g.title" :title="g.title">
      <JobCard v-for="job in g.items" :key="job.name" :name="job.name" />
    </Panel>
  </template>
</template>
