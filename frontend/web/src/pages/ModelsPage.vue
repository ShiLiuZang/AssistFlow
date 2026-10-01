<!-- 分类器管理：九项验收、数据与产物、评测与阈值、错例复核、单句试分类 -->
<script setup lang="ts">
import PageHeader from '../components/PageHeader.vue'
import TabBar from '../components/TabBar.vue'
import { useUrlState } from '../composables/useUrlState'
import AcceptanceTab from './models/AcceptanceTab.vue'
import DataTab from './models/DataTab.vue'
import EvalTab from './models/EvalTab.vue'
import ErrorsTab from './models/ErrorsTab.vue'
import TrialTab from './models/TrialTab.vue'

const tabs: [string, string][] = [
  ['acceptance', '九项验收'],
  ['data', '数据与产物'],
  ['eval', '评测与阈值'],
  ['errors', '错例复核'],
  ['trial', '单句试分类'],
]
const tab = useUrlState('tab', 'acceptance')
</script>

<template>
  <PageHeader eyebrow="CLASSIFIER MANAGEMENT" title="分类器管理" desc="核对数据、评测与产物，分别判断验收结果和服务状态。" />
  <TabBar v-model="tab" :tabs="tabs" />
  <AcceptanceTab v-if="tab === 'acceptance'" />
  <DataTab v-else-if="tab === 'data'" />
  <EvalTab v-else-if="tab === 'eval'" />
  <ErrorsTab v-else-if="tab === 'errors'" />
  <TrialTab v-else />
</template>
