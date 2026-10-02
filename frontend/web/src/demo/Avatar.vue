<script setup lang="ts">
defineProps<{ name: string; color?: string; small?: boolean }>()
</script>

<template>
  <span class="avatar" :class="[color, { small }]">{{ name.slice(0, 1) }}</span>
</template>
