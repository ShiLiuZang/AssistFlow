<!-- 管理总览（对应 V2 admin-data.js 的 overviewPage） -->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { getAdminOverview } from '../api/endpoints'
import DataPage from '../components/DataPage.vue'
import DataState from '../components/DataState.vue'
import Icon from '../components/Icon.vue'
import StatusPill from '../components/StatusPill.vue'
import { reportDataTime } from '../composables/useDataTime'

const router = useRouter()
const { data, error, isPending, dataUpdatedAt } = useQuery({ queryKey: ['admin', 'overview'], queryFn: getAdminOverview })
watch(dataUpdatedAt, reportDataTime, { immediate: true })

const routes: Record<string, string> = {
  kb: '/knowledge',
  review: '/review',
  rageval: '/quality',
  observability: '/observability',
  topics: '/topics',
  classifier: '/models',
}
const icons: Record<string, string> = { kb: 'book', review: 'search', rageval: 'shield', observability: 'chart', topics: 'chat', classifier: 'spark' }
const titles: Record<string, string> = { kb: '知识中心', review: '知识缺口', rageval: 'RAG 质量', classifier: '分类器管理' }
const stateLabel: Record<string, [string, string]> = {
  ok: ['正常', ''],
  attention: ['需关注', 'amber'],
  missing: ['尚无数据', 'neutral'],
  error: ['读取失败', 'red'],
}
const attention = computed(() => (data.value?.modules ?? []).filter((m) => m.status === 'attention' || m.status === 'error'))
const value = (v: unknown) => (v === null || v === undefined ? '—' : String(v))
</script>

<template>
  <DataPage page="overview">
    <template #actions>
      <button class="btn primary" @click="router.push('/knowledge')">打开知识中心</button>
    </template>

    <DataState :loading="isPending" :error="error" />
    <div v-if="data" class="overview-layout admin-overview">
      <div v-if="attention.length" class="overview-attention" aria-label="需关注的模块">
        <strong>{{ attention.length }} 个模块需关注</strong>
        <button v-for="row in attention" :key="row.key" class="text-button" @click="router.push(routes[row.key] ?? '/overview')">{{ titles[row.key] ?? row.title }} <Icon name="arrow" /></button>
      </div>
      <div>
        <div class="overview-heading">
          <h2>管理工作区</h2>
          <span class="small muted">六个模块，分别读取业务状态</span>
        </div>
        <div class="overview-ledger">
          <article v-for="row in data.modules" :key="row.key" class="overview-module" :class="{ 'module-error': row.status === 'error' }">
            <div class="overview-module-name"><Icon :name="icons[row.key] ?? 'chart'" /><h2>{{ titles[row.key] ?? row.title }}</h2><StatusPill :color="stateLabel[row.status]?.[1] ?? 'neutral'">{{ stateLabel[row.status]?.[0] ?? '未知' }}</StatusPill></div>
            <div class="overview-module-description"><p>{{ row.headline }}</p><details><summary>数据说明</summary><small>{{ row.note || row.lede || '查看详细业务状态' }}</small></details></div>
            <div class="overview-module-metrics">
              <span v-for="m in row.metrics" :key="m.label"><b>{{ value(m.value) }}</b>{{ m.label }}</span>
              <span v-if="!row.metrics.length" class="muted">等待读数或报告</span>
            </div>
            <RouterLink class="overview-module-link" :to="routes[row.key] ?? '/overview'">查看详情 <Icon name="arrow" /></RouterLink>
          </article>
        </div>
      </div>
      <p class="field-hint">库存、报告和运行状态分别读取；未知值保留为 —。点击模块核对明细。</p>
    </div>
  </DataPage>
</template>
