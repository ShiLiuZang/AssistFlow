<!-- 知识中心：顶部库存统计 + 五个分区（tab 状态同步在 URL 的 ?tab= 上） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getKbOverview } from '../api/endpoints'
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import StateBlock from '../components/StateBlock.vue'
import TabBar from '../components/TabBar.vue'
import { useUrlState } from '../composables/useUrlState'
import { clock } from '../utils/format'
import ContentTab from './knowledge/ContentTab.vue'
import ImportTab from './knowledge/ImportTab.vue'
import MiningTab from './knowledge/MiningTab.vue'
import IndexTab from './knowledge/IndexTab.vue'
import SearchTab from './knowledge/SearchTab.vue'

const tabs: [string, string][] = [
  ['content', '知识内容'],
  ['import', '录入与切块'],
  ['mining', '候选问答'],
  ['index', '索引状态'],
  ['search', '检索自测'],
]
const tab = useUrlState('tab', 'content')

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
</script>

<template>
  <PageHeader eyebrow="KNOWLEDGE OPERATIONS" title="知识中心" desc="维护回复依据，核对原文、审核与向量状态。">
    <button class="btn" type="button" :disabled="isFetching" @click="refetch()">
      {{ isFetching ? '刷新中…' : '刷新读数' }}
    </button>
    <button class="btn primary" type="button" @click="tab = 'import'">录入内容</button>
  </PageHeader>

  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />

  <template v-if="data">
    <p v-if="data.db_error" class="notice error">数据库读取失败：{{ data.db_error }}</p>
    <section class="stat-strip" aria-label="知识库存统计">
      <StatCard label="知识块总数" :value="data.chunks.total" unit="块" foot="数据库原文记录（MySQL）" />
      <StatCard label="已向量化" :value="data.chunks.done" unit="块" foot="MySQL 中标记已向量化" />
      <StatCard label="待向量化" :value="data.chunks.pending" unit="块" foot="保留原文，等待补齐" />
      <StatCard label="关键条款" :value="data.chunks.key_clause" unit="块" foot="需完整保留的约束" />
      <StatCard label="Milvus 条数" :value="milvusValue" unit="条" foot="向量库实际记录数" />
      <StatCard label="双写核对" :value="consistency.text" :foot="consistency.foot" :tone="consistency.tone" />
    </section>
    <p class="muted small updated">读数时间 {{ clock(dataUpdatedAt) }}</p>
  </template>

  <TabBar v-model="tab" :tabs="tabs" />
  <ContentTab v-if="tab === 'content'" />
  <ImportTab v-else-if="tab === 'import'" :overview="data" />
  <MiningTab v-else-if="tab === 'mining'" />
  <IndexTab v-else-if="tab === 'index'" :overview="data" />
  <SearchTab v-else-if="tab === 'search'" />
</template>

<style scoped>
.updated {
  margin: -12px 0 16px;
}
</style>
