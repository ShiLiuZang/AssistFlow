<!-- 报告空状态：附"查看运行说明" -->
<script setup lang="ts">
import Icon from '../../components/Icon.vue'
import { openGuide } from './guide'
defineProps<{ title: string; description: string }>()
</script>

<template>
  <div class="data-empty-state">
    <span><Icon name="file" /></span>
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
    <button class="btn" @click="openGuide">查看运行说明</button>
  </div>
</template>
