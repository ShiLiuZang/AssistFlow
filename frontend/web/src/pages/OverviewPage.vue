<!-- 管理总览：六个模块各自的健康状态，点击进入对应页面 -->
<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { getAdminOverview } from '../api/endpoints'
import PageHeader from '../components/PageHeader.vue'
import Pill from '../components/Pill.vue'
import StateBlock from '../components/StateBlock.vue'
import { moduleStatus } from '../utils/labels'
import { clock, num } from '../utils/format'

const { data, error, isPending, isFetching, refetch, dataUpdatedAt } = useQuery({
  queryKey: ['admin', 'overview'],
  queryFn: getAdminOverview,
})

// 后端返回的是旧页面路径，这里换成新路由
const routeByKey: Record<string, string> = {
  kb: '/knowledge',
  rageval: '/quality',
  review: '/review',
  observability: '/observability',
  topics: '/topics',
  classifier: '/models',
}
</script>

<template>
  <PageHeader eyebrow="SERVICE OPERATIONS" title="管理总览" desc="查看知识、质量与模型的当前状态，找到下一件需要处理的事。">
    <button class="btn" type="button" :disabled="isFetching" @click="refetch()">
      {{ isFetching ? '刷新中…' : '刷新读数' }}
    </button>
  </PageHeader>

  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />

  <template v-if="data">
    <div class="grid-3">
      <RouterLink v-for="m in data.modules" :key="m.key" :to="routeByKey[m.key] ?? '/overview'" class="card">
        <div class="card-top">
          <h2>{{ m.title }}</h2>
          <Pill :tone="moduleStatus[m.status][1]">{{ moduleStatus[m.status][0] }}</Pill>
        </div>
        <p class="headline">{{ m.headline }}</p>
        <dl v-if="m.metrics.length" class="metrics">
          <div v-for="metric in m.metrics" :key="metric.label">
            <dt>{{ metric.label }}</dt>
            <dd>{{ num(metric.value) }}</dd>
          </div>
        </dl>
        <p v-if="m.note" class="note">{{ m.note }}</p>
      </RouterLink>
    </div>
    <p class="muted small">读数时间 {{ clock(dataUpdatedAt) }}。缺失项显示"—"，不以零值代替。</p>
  </template>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  color: inherit;
  text-decoration: none;
  transition: border-color 150ms, box-shadow 150ms;
}
.card:hover {
  border-color: var(--brand);
  box-shadow: var(--small-shadow);
}
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
h2 {
  font-size: 17px;
}
.headline {
  margin: 0;
  color: var(--muted);
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin: 0;
}
.metrics dt {
  font-size: 12px;
  color: var(--muted);
}
.metrics dd {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.note {
  margin: auto 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  font-size: 12px;
  color: var(--muted);
}
</style>
