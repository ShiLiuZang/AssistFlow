<!-- 迁移过渡页：演示页面尚未迁移到 Vue 时显示 -->
<script setup lang="ts">
import { useRoute } from 'vue-router'
import Icon from '../components/Icon.vue'
const route = useRoute()
</script>

<template>
  <div class="page admin-page">
    <div class="data-empty-state">
      <Icon name="clock" />
      <h2>{{ route.meta.title }} · 待迁移</h2>
      <p>这个演示页面还在从 V2 迁移到 Vue，迁移完成后会和 V2 保持一致。</p>
    </div>
  </div>
</template>
