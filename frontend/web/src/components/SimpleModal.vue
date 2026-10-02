<!-- 只有说明文字的弹窗内容：body 为受信任的静态 HTML（仅用于本项目写死的说明文案） -->
<script setup lang="ts">
import { closeModal } from '../composables/useModal'
defineProps<{ html: string; closeText?: string }>()
</script>

<template>
  <div class="modal-body" v-html="html" />
  <div class="modal-foot">
    <button class="btn" @click="closeModal">{{ closeText ?? '知道了' }}</button>
  </div>
</template>
