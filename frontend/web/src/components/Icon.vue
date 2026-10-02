<script setup lang="ts">
import { iconPaths, type IconName } from '../v2/icons'
defineProps<{ name: IconName | string }>()
</script>

<template>
  <svg
    class="icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="iconPaths[name as IconName] ?? iconPaths.chat" />
  </svg>
</template>
