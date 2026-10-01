<!-- 挂在 App 里的全局确认弹窗，由 composables/useConfirm.ts 控制 -->
<script setup lang="ts">
import { computed } from 'vue'
import AppDialog from './AppDialog.vue'
import { confirmState, settleConfirm } from '../composables/useConfirm'

const open = computed({
  get: () => confirmState.open,
  set: (value: boolean) => {
    if (!value) settleConfirm(false)
  },
})
</script>

<template>
  <AppDialog v-model="open" :title="confirmState.options.title">
    <p class="text">{{ confirmState.options.body }}</p>
    <template #footer>
      <button class="btn" type="button" @click="settleConfirm(false)">取消</button>
      <button class="btn" :class="confirmState.options.danger ? 'danger' : 'primary'" type="button" @click="settleConfirm(true)">
        {{ confirmState.options.confirmText ?? '确认' }}
      </button>
    </template>
  </AppDialog>
</template>

<style scoped>
.text {
  margin: 0;
  white-space: pre-line;
}
</style>
