<!-- 演示页标题 + "演示工作区"提示条（对应 V2 service-panels heading） -->
<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; desc: string }>()
</script>

<template>
  <div class="page-title between">
    <div>
      <div class="eyebrow">{{ eyebrow }}</div>
      <h1>{{ title }}</h1>
      <p>{{ desc }}</p>
    </div>
    <div class="page-actions"><slot /></div>
  </div>
  <div class="demo-strip"><span class="dot amber"></span>演示工作区 · 数据与修改仅在当前页面会话中保留，刷新后重置。</div>
</template>
