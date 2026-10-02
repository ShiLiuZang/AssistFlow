<!-- V2 的统计格：标签 / 大数字 + 单位 / 说明。值为空显示"—"，不补 0 -->
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ label: string; value?: unknown; unit?: string; foot?: string }>()
const display = computed(() => (props.value === null || props.value === undefined ? '—' : String(props.value)))
</script>

<template>
  <div class="stat">
    <div class="stat-label">{{ label }}</div>
    <div class="stat-number">{{ display }}<span>{{ unit ?? '' }}</span></div>
    <div class="stat-foot">{{ foot ?? '' }}</div>
  </div>
</template>
