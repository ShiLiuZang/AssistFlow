<!-- 通用弹窗（原生 <dialog>）。v-model 控制开关，Esc 和遮罩点击都能关闭 -->
<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'

defineProps<{ title: string; wide?: boolean }>()
const open = defineModel<boolean>({ required: true })
const el = ref<HTMLDialogElement | null>(null)

function sync() {
  if (!el.value) return
  if (open.value && !el.value.open) el.value.showModal()
  if (!open.value && el.value.open) el.value.close()
}
watch(open, sync)
onMounted(sync)

function onBackdrop(event: MouseEvent) {
  if (event.target === el.value) open.value = false
}
</script>

<template>
  <dialog ref="el" :class="{ wide }" :aria-label="title" @close="open = false" @click="onBackdrop">
    <div class="box">
      <header>
        <h2>{{ title }}</h2>
        <button class="close" type="button" aria-label="关闭" @click="open = false">×</button>
      </header>
      <div class="body"><slot /></div>
      <footer v-if="$slots.footer"><slot name="footer" /></footer>
    </div>
  </dialog>
</template>

<style scoped>
dialog {
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100vh - 64px);
  padding: 0;
  border: 0;
  border-radius: 12px;
  box-shadow: var(--shadow);
  color: var(--ink);
  overscroll-behavior: contain;
}
dialog.wide {
  width: min(920px, calc(100vw - 32px));
}
dialog::backdrop {
  background: rgb(33 57 65 / 35%);
}
.box {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 64px);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
}
h2 {
  font-size: 17px;
}
.close {
  border: 0;
  background: none;
  font-size: 22px;
  line-height: 1;
  color: var(--muted);
}
.body {
  padding: 16px 20px;
  overflow: auto;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--line);
}
</style>
