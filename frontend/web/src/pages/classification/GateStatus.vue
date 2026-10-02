<script setup lang="ts">
import StatusPill from '../../components/StatusPill.vue'
defineProps<{ status?: string }>()
const names: Record<string, string> = { pass: '达标', fail: '未达标', missing: '未生成' }
</script>

<template>
  <StatusPill :color="status === 'fail' ? 'red' : status === 'pass' ? '' : 'neutral'">{{ (status && names[status]) || '未知' }}</StatusPill>
</template>
