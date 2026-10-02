<!-- 知识中心（对应 V2 admin-data.js）：五个分区，当前分区写在 URL 的 ?tab= 上 -->
<script setup lang="ts">
import { nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { getKbOverview } from '../api/endpoints'
import DataPage from '../components/DataPage.vue'
import Icon from '../components/Icon.vue'
import { reportDataTime } from '../composables/useDataTime'
import { useUrlState } from '../composables/useUrlState'
import { kb } from './knowledge/state'
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
const route = useRoute()
const router = useRouter()
const overview = useQuery({ queryKey: ['kb', 'overview'], queryFn: getKbOverview })
watch(overview.dataUpdatedAt, reportDataTime, { immediate: true })

async function openMaterials() {
  await router.replace({ query: { ...route.query, tab: 'import' } })
  await nextTick()
  const el = document.getElementById('data-source-materials')
  if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 16, behavior: 'smooth' })
}
const busy = () => kb.ingestBusy || kb.vectorChecking || kb.vectorStarting
</script>

<template>
  <DataPage page="knowledge" :busy="busy()">
    <template #actions>
      <button class="btn soft" @click="tab = 'index'">向量化<span v-if="overview.data.value?.chunks.pending"> · {{ overview.data.value.chunks.pending }} 待补</span></button>
      <button class="btn soft" @click="openMaterials">建库材料</button>
      <button class="btn primary" @click="tab = 'import'"><Icon name="plus" />录入内容</button>
    </template>

    <nav class="section-tabs" aria-label="知识中心子页面">
      <button
        v-for="[key, label] in tabs"
        :key="key"
        :class="{ active: tab === key }"
        :aria-current="tab === key ? 'page' : 'false'"
        @click="tab = key"
      >
        {{ label }}
      </button>
    </nav>
    <ContentTab v-if="tab === 'content'" :overview="overview" />
    <ImportTab v-else-if="tab === 'import'" :overview="overview" @materials="openMaterials" />
    <MiningTab v-else-if="tab === 'mining'" />
    <IndexTab v-else-if="tab === 'index'" :overview="overview" />
    <SearchTab v-else-if="tab === 'search'" />
  </DataPage>
</template>
