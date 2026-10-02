<script setup lang="ts">
defineProps<{ alert?: boolean }>()
</script>

<template>
  <div class="notice report-note" :class="{ amber: alert }" :role="alert ? 'alert' : undefined"><slot /></div>
</template>
