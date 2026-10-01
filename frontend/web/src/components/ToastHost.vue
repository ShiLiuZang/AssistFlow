<script setup lang="ts">
import { toastState } from '../composables/useToast'
</script>

<template>
  <div class="toast-region" role="status" aria-live="polite">
    <div v-if="toastState.message" :key="toastState.id" class="toast" :class="toastState.tone">
      {{ toastState.message }}
    </div>
  </div>
</template>

<style scoped>
.toast-region {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 50;
  max-width: min(420px, calc(100vw - 40px));
}
.toast {
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--rail);
  color: var(--rail-text);
  box-shadow: var(--shadow);
}
.toast.error {
  background: var(--red);
  color: #fff;
}
</style>
