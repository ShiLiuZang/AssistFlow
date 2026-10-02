<script setup lang="ts">
defineProps<{ items: [string, unknown][] }>()
</script>

<template>
  <div class="report-meta">
    <span v-for="[k, v] in items" :key="k"
      >{{ k }}<strong>{{ v == null ? '—' : v }}</strong></span
    >
  </div>
</template>
