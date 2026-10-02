<!-- 分类器管理（对应 V2 admin-classification.js 的 modelsPage） -->
<script setup lang="ts">
import { computed } from 'vue'
import DataPage from '../components/DataPage.vue'
import { useUrlState } from '../composables/useUrlState'
import { openClsGuide } from './classification/guide'
import AcceptanceTab from './models/AcceptanceTab.vue'
import DataTab from './models/DataTab.vue'
import ErrorsTab from './models/ErrorsTab.vue'
import EvalTab from './models/EvalTab.vue'
import TrialTab from './models/TrialTab.vue'

const tabs = [
  ['acceptance', '九项验收'],
  ['data', '数据与产物'],
  ['evaluation', '评测与阈值'],
  ['errors', '错例复核'],
  ['trial', '单句试分类'],
] as const
const tab = useUrlState('tab', 'acceptance')
const current = computed(() => (tabs.some(([k]) => k === tab.value) ? tab.value : 'acceptance'))
const setTab = (key: string) => (tab.value = key)
</script>

<template>
  <DataPage page="models">
    <template #actions>
      <button class="btn soft" @click="openClsGuide">查看查询范围</button>
    </template>
    <nav class="section-tabs" aria-label="分类器管理子页面">
      <button v-for="[key, title] in tabs" :key="key" :class="{ active: current === key }" :aria-current="current === key ? 'page' : 'false'" @click="setTab(key)">{{ title }}</button>
    </nav>
    <div class="cls-report">
      <AcceptanceTab v-if="current === 'acceptance'" @tab="setTab" />
      <DataTab v-else-if="current === 'data'" />
      <EvalTab v-else-if="current === 'evaluation'" @tab="setTab" />
      <ErrorsTab v-else-if="current === 'errors'" />
      <TrialTab v-else />
    </div>
  </DataPage>
</template>
