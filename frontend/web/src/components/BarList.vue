<!-- 横向条形图：用于分布对比。value 为空时显示"—"，不画条 -->
<script setup lang="ts">
import { computed } from 'vue'
import { num } from '../utils/format'

const props = defineProps<{ items: { label: string; value: number | null; note?: string }[] }>()
const max = computed(() => Math.max(1, ...props.items.map((i) => i.value ?? 0)))
</script>

<template>
  <ul class="bars">
    <li v-for="item in items" :key="item.label">
      <span class="label">{{ item.label }}</span>
      <span class="track">
        <span v-if="item.value" class="fill" :style="{ width: `${(item.value / max) * 100}%` }" />
      </span>
      <span class="value">{{ num(item.value) }}<small v-if="item.note"> {{ item.note }}</small></span>
    </li>
  </ul>
</template>

<style scoped>
.bars {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
li {
  display: grid;
  grid-template-columns: minmax(80px, 140px) 1fr auto;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
.label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track {
  height: 10px;
  background: var(--sand);
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  background: var(--brand);
  border-radius: 999px;
}
.value {
  font-variant-numeric: tabular-nums;
  min-width: 48px;
  text-align: right;
}
small {
  color: var(--muted);
}
</style>
