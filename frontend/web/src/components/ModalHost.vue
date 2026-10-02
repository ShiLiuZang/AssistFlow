<!-- 全局弹窗宿主：沿用 V2 的 <dialog id="modal"> / #modal-content / .modal-head 结构 -->
<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import Icon from './Icon.vue'
import { closeModal, modalState } from '../composables/useModal'

const el = ref<HTMLDialogElement | null>(null)
function sync() {
  if (!el.value) return
  if (modalState.open && !el.value.open) el.value.showModal()
  if (!modalState.open && el.value.open) el.value.close()
}
watch(() => modalState.open, sync)
onMounted(sync)
</script>

<template>
  <dialog id="modal" ref="el" :class="modalState.cls" aria-labelledby="modal-title" @close="closeModal">
    <div id="modal-content">
      <template v-if="modalState.view">
        <div class="modal-head">
          <h2 id="modal-title">{{ modalState.title }}</h2>
          <button class="icon-btn" aria-label="关闭对话框" @click="closeModal"><Icon name="close" /></button>
        </div>
        <component :is="modalState.view" :key="modalState.key" v-bind="modalState.props" />
      </template>
    </div>
  </dialog>
</template>
