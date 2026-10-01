<!-- 加载中 / 失败 / 空 三种状态的统一展示 -->
<script setup lang="ts">
defineProps<{ loading?: boolean; error?: Error | null; empty?: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="loading" class="state" role="status">正在读取后台数据…</div>
  <div v-else-if="error" class="state error" role="alert">
    <strong>暂时无法读取数据</strong>
    <p>{{ error.message }}</p>
    <button class="btn" type="button" @click="$emit('retry')">重新读取</button>
  </div>
  <div v-else-if="empty" class="state">{{ empty }}</div>
</template>

<style scoped>
.state {
  padding: 28px 16px;
  text-align: center;
  color: var(--muted);
}
.error strong {
  color: var(--red);
}
.error p {
  margin: 6px 0 12px;
}
</style>
