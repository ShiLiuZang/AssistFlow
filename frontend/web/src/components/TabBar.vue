<!-- 页内 tab。v-model 绑定当前 tab 的 key -->
<script setup lang="ts">
defineProps<{ tabs: [string, string][] }>()
const model = defineModel<string>({ required: true })
</script>

<template>
  <nav class="tabs" aria-label="页面分区">
    <button
      v-for="[key, label] in tabs"
      :key="key"
      type="button"
      :class="{ active: model === key }"
      :aria-current="model === key ? 'page' : undefined"
      @click="model = key"
    >
      {{ label }}
    </button>
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--line-strong);
  margin-bottom: 20px;
  overflow-x: auto;
  scrollbar-width: none;
}
button {
  border: 0;
  background: none;
  padding: 10px 12px;
  color: var(--muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
}
button:hover {
  color: var(--ink);
}
button.active {
  color: var(--brand-deep);
  border-bottom-color: var(--brand);
  font-weight: 600;
}
</style>
