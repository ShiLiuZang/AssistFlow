<script setup lang="ts">
defineProps<{ values?: string[]; other?: string[]; missing?: boolean }>()
</script>

<template>
  <span v-if="!Array.isArray(values) || !values.length" class="muted">无标签</span>
  <div v-else class="tag-row">
    <span v-for="label in values" :key="label" class="cls-compare-tag" :class="(other || []).includes(label) ? 'correct' : missing ? 'missed' : 'extra'">{{ label }}</span>
  </div>
</template>
