<script setup lang="ts">
defineProps<{ items: [string, unknown][] }>()
</script>

<template>
  <div class="report-meta">
    <span v-for="[label, value] in items" :key="label"
      >{{ label }}<strong>{{ value == null ? '—' : value }}</strong></span
    >
  </div>
</template>
