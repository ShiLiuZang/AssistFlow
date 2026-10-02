<script setup lang="ts">
import { closeModal } from '../../composables/useModal'
const props = defineProps<{ onConfirm: () => void }>()
function confirm() {
  closeModal()
  props.onConfirm()
}
</script>

<template>
  <div class="modal-body"><p>结束后，后续消息将恢复由 AI 助手接待。已创建的工单继续保留，不会自动标记为解决。</p></div>
  <div class="modal-foot"><button class="btn" @click="closeModal">继续接待</button><button class="btn primary" @click="confirm">确认结束</button></div>
</template>
