<!-- 引用的知识（服务侧只读查看） -->
<script setup lang="ts">
import { computed } from 'vue'
import StatusPill from '../components/StatusPill.vue'
import { closeModal } from '../composables/useModal'
import { demo, docColor, docLabel } from './store'
const props = defineProps<{ id: number }>()
const d = computed(() => demo.docs.find((x) => x.id === props.id)!)
</script>

<template>
  <div class="modal-body">
    <div class="between" style="margin-bottom: 18px">
      <StatusPill :color="docColor(d)">{{ docLabel(d) }}</StatusPill><span class="small muted">{{ d.category }} · {{ d.version }} · {{ d.scope }}</span>
    </div>
    <div class="preview-text" style="white-space: pre-line">{{ d.text }}</div>
    <p class="field-hint">演示政策 · 用于页面和引用样式预览，不代表实际店铺承诺。</p>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">关闭</button></div>
</template>
