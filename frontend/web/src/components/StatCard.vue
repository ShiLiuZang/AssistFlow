<!--
  统计卡片：一个大数字 + 单位 + 一行出处说明。
  对应旧 V2 里的 metric() / stat() 字符串拼接函数，现在变成可复用的组件。
-->
<script setup lang="ts">
import { computed } from 'vue'

// defineProps：声明父组件可以传进来的参数，以及它们的类型
const props = defineProps<{
  label: string
  value: number | string | null | undefined
  unit?: string
  foot?: string
  tone?: 'normal' | 'warn'
}>()

// computed：根据 props 自动算出显示值，props 变了它会自动重算
// 缺失值显示"—"，不补 0（沿用 V2 的约定）
const display = computed(() => (props.value === null || props.value === undefined ? '—' : props.value))
const showUnit = computed(() => typeof props.value === 'number' && props.unit)
</script>

<template>
  <div class="stat" :class="{ warn: tone === 'warn' }">
    <div class="label">{{ label }}</div>
    <div class="number">
      {{ display }}<span v-if="showUnit" class="unit">{{ unit }}</span>
    </div>
    <div v-if="foot" class="foot">{{ foot }}</div>
  </div>
</template>

<style scoped>
.stat {
  padding: 4px 20px;
  border-left: 1px solid var(--line);
  min-width: 0;
}
.stat:first-child {
  border-left: 0;
}
.label {
  font-size: 12px;
  color: var(--muted);
}
.number {
  font-size: 30px;
  font-weight: 600;
  line-height: 1.4;
  font-variant-numeric: tabular-nums;
}
.unit {
  font-size: 12px;
  font-weight: 400;
  color: var(--muted);
  margin-left: 6px;
}
.foot {
  font-size: 12px;
  color: var(--muted);
}
.warn .number {
  color: var(--amber);
}
</style>
