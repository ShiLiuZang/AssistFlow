<script setup lang="ts">
import type { EvalCase } from '../../api/types'
import EvidenceGroups from './EvidenceGroups.vue'
import ModalFoot from './ModalFoot.vue'
import ReportMeta from './ReportMeta.vue'
import { judge } from './state'
defineProps<{ item: EvalCase }>()
</script>

<template>
  <div class="modal-body">
    <h3>{{ item.query }}</h3>
    <ReportMeta
      :items="[
        ['题目 ID', item.id],
        ['标准判断', judge(item.should_refuse)],
      ]"
    />
    <h3>期望证据组</h3>
    <EvidenceGroups :item="item" />
    <p class="field-hint section-gap">预期关键词：{{ item.expected_terms?.join('、') || '无' }}</p>
  </div>
  <ModalFoot />
</template>
