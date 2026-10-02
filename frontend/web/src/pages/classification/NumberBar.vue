<script setup lang="ts">
import { computed } from 'vue'
import { dec, finite, formatted } from './shared'
const props = withDefaults(defineProps<{ value?: number | null; max?: number; alert?: boolean; precision?: boolean }>(), { max: 1, precision: true })
const width = computed(() => (finite(props.value) && finite(props.max) && props.max > 0 ? Math.max(0, Math.min(100, (props.value / props.max) * 100)) : 0))
</script>

<template>
  <div class="cls-number-bar" :class="{ 'is-alert': alert }">
    <span>{{ precision ? dec(value) : formatted(value) }}</span>
    <div class="cls-bar-track" aria-hidden="true"><i :style="{ width: width + '%' }"></i></div>
  </div>
</template>
