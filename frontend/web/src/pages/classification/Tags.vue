<script setup lang="ts">
import StatusPill from '../../components/StatusPill.vue'
defineProps<{ values?: string[] | null }>()
</script>

<template>
  <div v-if="Array.isArray(values) && values.length" class="tag-row"><StatusPill v-for="v in values" :key="v" color="neutral">{{ v }}</StatusPill></div>
  <span v-else class="muted">—</span>
</template>
