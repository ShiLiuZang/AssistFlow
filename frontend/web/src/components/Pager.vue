<script setup lang="ts">
defineProps<{ page: number; pages: number; total: number }>()
defineEmits<{ go: [page: number] }>()
</script>

<template>
  <div class="pager">
    <span>共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页</span>
    <div class="buttons">
      <button class="btn small" type="button" :disabled="page <= 1" @click="$emit('go', page - 1)">上一页</button>
      <button class="btn small" type="button" :disabled="page >= pages" @click="$emit('go', page + 1)">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-top: 14px;
  font-size: 12px;
  color: var(--muted);
}
.buttons {
  display: flex;
  gap: 6px;
}
</style>
