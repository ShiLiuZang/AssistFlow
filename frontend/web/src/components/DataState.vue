<!-- 加载中 / 读取失败（对应 V2 的 emptyState / loadingOrError） -->
<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import Icon from './Icon.vue'
defineProps<{ loading?: boolean; error?: Error | null }>()
const client = useQueryClient()
</script>

<template>
  <div v-if="loading" class="data-empty-state" role="status">
    <Icon name="clock" />
    <h2>正在读取后台数据</h2>
    <p>库存、报告和列表将使用真实接口返回值。</p>
  </div>
  <div v-else-if="error" class="data-empty-state">
    <Icon name="info" />
    <h2>暂时无法读取数据</h2>
    <p>{{ error.message }}</p>
    <button class="btn" @click="client.invalidateQueries()">重新读取</button>
  </div>
</template>
