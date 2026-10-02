<script setup lang="ts">
import type { SourceFeatures } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
defineProps<{ features?: SourceFeatures | null }>()
</script>

<template>
  <span v-if="!features">—</span>
  <div v-else class="data-source-features">
    <StatusPill v-if="features.table_split">拆表</StatusPill>
    <StatusPill v-if="features.overlap">重叠</StatusPill>
    <StatusPill color="neutral">{{ features.sections ?? '—' }} 节</StatusPill>
  </div>
</template>
