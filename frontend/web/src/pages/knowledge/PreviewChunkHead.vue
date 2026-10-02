<script setup lang="ts">
import type { PreviewChunk } from '../../api/types'
import StatusPill from '../../components/StatusPill.vue'
defineProps<{ row: PreviewChunk }>()
</script>

<template>
  <div class="between data-preview-heading">
    <strong>{{ row.seq }}. {{ row.section_path }}</strong>
    <div class="data-chunk-labels">
      <StatusPill v-if="row.is_key_clause" color="red">关键条款</StatusPill>
      <StatusPill v-if="row.duplicate == null" color="neutral">未查重</StatusPill>
      <StatusPill v-else-if="row.duplicate" color="amber">重复</StatusPill>
      <StatusPill v-else>未发现重复</StatusPill>
    </div>
  </div>
</template>
