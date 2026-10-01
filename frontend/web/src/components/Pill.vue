<script setup lang="ts">
import type { Tone } from '../utils/labels'
defineProps<{ tone?: Tone }>()
</script>

<template>
  <span class="pill" :class="tone ?? 'neutral'"><slot /></span>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}
.green {
  background: var(--brand-soft);
  color: var(--brand-deep);
}
.amber {
  background: var(--amber-soft);
  color: #85592c;
}
.red {
  background: var(--red-soft);
  color: var(--red);
}
.blue {
  background: var(--blue-soft);
  color: var(--blue);
}
.neutral {
  background: var(--sand);
  color: var(--muted);
}
</style>
