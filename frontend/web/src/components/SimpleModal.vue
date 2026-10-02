<!-- 只有说明文字的弹窗内容：body 为受信任的静态 HTML（仅用于本项目写死的说明文案） -->
<script setup lang="ts">
import { useRouter } from 'vue-router'
import Icon from './Icon.vue'
import { closeModal } from '../composables/useModal'
const props = defineProps<{ html: string; closeText?: string; link?: { label: string; to: string } }>()
const router = useRouter()
function follow() {
  closeModal()
  if (props.link) router.push(props.link.to)
}
</script>

<template>
  <div class="modal-body" v-html="html" />
  <div class="modal-foot">
    <button class="btn" @click="closeModal">{{ closeText ?? '知道了' }}</button>
    <button v-if="link" class="btn soft" @click="follow">{{ link.label }} <Icon name="arrow" /></button>
  </div>
</template>
