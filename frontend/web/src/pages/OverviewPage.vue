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
    <div v-if="data" class="overview-layout">
      <div>
        <div class="overview-heading">
          <h2>管理工作区</h2>
          <span class="small muted">六个模块，分别读取业务状态</span>
        </div>
        <div class="module-grid">
          <button v-for="row in data.modules" :key="row.key" class="module-card data-module" @click="router.push(routes[row.key] ?? '/overview')">
            <div class="module-card-top">
              <span class="module-icon"><Icon :name="icons[row.key] ?? 'chart'" /></span>
              <StatusPill :color="stateLabel[row.status]?.[1] ?? 'neutral'">{{ stateLabel[row.status]?.[0] ?? '未知' }}</StatusPill>
            </div>
            <h2>{{ titles[row.key] ?? row.title }}</h2>
            <p>{{ row.headline }}</p>
            <div class="data-module-metrics">
              <span v-for="m in row.metrics" :key="m.label">{{ m.label }} <b>{{ value(m.value) }}</b></span>
              <span v-if="!row.metrics.length" class="muted">等待读数或报告</span>
            </div>
            <small>{{ row.note || row.lede || '查看详细业务状态' }}</small>
          </button>
        </div>
      </div>
      <aside>
        <section class="aside-panel">
          <div class="eyebrow">需要关注</div>
          <h3>从这里开始处理</h3>
          <button v-for="row in attention" :key="row.key" class="todo-row" @click="router.push(routes[row.key] ?? '/knowledge')">
            <span>{{ row.title }}<small>{{ row.headline }}</small></span><Icon name="arrow" />
          </button>
          <p v-if="!attention.length" class="small muted section-gap">当前没有读到需关注事项。</p>
          <button class="todo-row" @click="router.push('/knowledge')">
            <span>核对知识与索引<small>原文、待向量化与向量数量</small></span><Icon name="arrow" />
          </button>
        </section>
        <section class="aside-panel data-scope-note">
          <h3>每个数字，都有来源</h3>
          <p>库存、报告和运行状态分别读取；未知值保留为 —。</p>
          <p>当前接入总览、知识、审核、作业、质量、观测、主题与分类器的只读数据。</p>
        </section>
      </aside>
    </div>
  </DataPage>
</template>
