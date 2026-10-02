<!-- V2 的 pill：默认绿色，amber / red / blue / neutral 为其他语义色 -->
<script setup lang="ts">
defineProps<{ color?: string }>()
</script>

<template>
  <span class="pill" :class="color"><slot /></span>
</template>
