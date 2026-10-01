<script setup lang="ts">
defineProps<{ title?: string }>()
</script>

<template>
  <section class="panel">
    <div v-if="title || $slots.extra" class="panel-head">
      <h2>{{ title }}</h2>
      <div class="extra"><slot name="extra" /></div>
    </div>
    <div class="panel-body"><slot /></div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  margin-bottom: 20px;
  min-width: 0;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
}
h2 {
  font-size: 16px;
}
.extra {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.panel-body {
  padding: 16px 20px;
}
</style>
