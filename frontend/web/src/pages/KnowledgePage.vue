<!-- 知识中心页面（第一步：只做顶部库存统计，数据来自真实接口 /api/kb/overview） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getKbOverview } from '../api/kb'
import StatCard from '../components/StatCard.vue'

// useQuery：发请求 + 缓存 + 加载/错误状态，一行搞定。
// queryKey 是这份数据在缓存里的名字，其他页面用同一个 key 会直接复用缓存。
const { data, error, isPending, isFetching, refetch, dataUpdatedAt } = useQuery({
  queryKey: ['kb', 'overview'],
  queryFn: getKbOverview,
})

const consistency = computed(() => {
  const c = data.value?.consistent
  if (c === true) return { text: '一致', foot: '数量一致不代表检索合格', tone: 'normal' as const }
  if (c === false) return { text: '对不上', foot: '有待补块或两端数量不同', tone: 'warn' as const }
  return { text: '未知', foot: '数据库或向量库不可用，暂不下结论', tone: 'normal' as const }
})

const milvusValue = computed(() => {
  const m = data.value?.milvus
  if (!m) return null
  return m.online ? m.count : '离线'
})

// 用 Intl 格式化时间，而不是手拼字符串
const timeFormat = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const updatedAt = computed(() => (dataUpdatedAt.value ? timeFormat.format(dataUpdatedAt.value) : ''))
</script>

<template>
  <header class="page-head">
    <div>
      <div class="eyebrow">KNOWLEDGE OPERATIONS</div>
      <h1>知识中心</h1>
      <p class="desc">维护回复依据，核对原文、审核与向量状态。</p>
    </div>
    <button class="btn" type="button" :disabled="isFetching" @click="refetch()">
      {{ isFetching ? '刷新中…' : '刷新读数' }}
    </button>
  </header>

  <!-- v-if / v-else-if / v-else：按状态显示不同内容 -->
  <section v-if="isPending" class="panel state" role="status">正在读取后台数据…</section>

  <section v-else-if="error" class="panel state error" role="alert">
    <strong>暂时无法读取数据</strong>
    <p>{{ error.message }}</p>
    <button class="btn" type="button" @click="refetch()">重新读取</button>
  </section>

  <template v-else-if="data">
    <p v-if="data.db_error" class="notice" role="status">数据库读取失败：{{ data.db_error }}</p>

    <section class="panel stat-strip" aria-label="知识库存统计">
      <StatCard label="知识块总数" :value="data.chunks.total" unit="块" foot="数据库原文记录（MySQL）" />
      <StatCard label="已向量化" :value="data.chunks.done" unit="块" foot="MySQL 中标记已向量化" />
      <StatCard label="待向量化" :value="data.chunks.pending" unit="块" foot="保留原文，等待补齐" />
      <StatCard label="关键条款" :value="data.chunks.key_clause" unit="块" foot="需完整保留的约束" />
      <StatCard label="Milvus 条数" :value="milvusValue" unit="条" foot="向量库实际记录数" />
      <StatCard label="双写核对" :value="consistency.text" :foot="consistency.foot" :tone="consistency.tone" />
    </section>

    <p class="updated">读数时间 {{ updatedAt }}</p>
  </template>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
}
.eyebrow {
  font-size: 12px;
  letter-spacing: 0.2em;
  color: var(--brand);
}
h1 {
  font-size: 30px;
}
.desc {
  margin: 6px 0 0;
  color: var(--muted);
}
.panel {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
.stat-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  row-gap: 16px;
  padding: 22px 4px;
}
.state {
  padding: 32px;
  text-align: center;
  color: var(--muted);
}
.state.error strong {
  color: var(--red);
}
.notice {
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--amber-soft);
  color: var(--amber);
}
.updated {
  font-size: 12px;
  color: var(--muted);
}
</style>
