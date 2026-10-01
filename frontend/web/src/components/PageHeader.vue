<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; desc?: string }>()
</script>

<template>
  <header class="page-head">
    <div>
      <div class="eyebrow">{{ eyebrow }}</div>
      <h1>{{ title }}</h1>
      <p v-if="desc" class="desc">{{ desc }}</p>
    </div>
    <div class="actions"><slot /></div>
  </header>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}
.eyebrow {
  font-size: 12px;
  letter-spacing: 0.2em;
  color: var(--brand);
}
h1 {
  font-size: 30px;
  line-height: 1.3;
}
.desc {
  margin: 6px 0 0;
  color: var(--muted);
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
