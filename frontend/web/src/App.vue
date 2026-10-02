<!-- 根组件：V2 顶部产品预览栏 + 三种视角（客户咨询页 / 客服工作台 / 管理后台） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from './components/AppShell.vue'
import ModalHost from './components/ModalHost.vue'
import ConfirmHost from './components/ConfirmHost.vue'
import { cyclePalette, paletteName } from './composables/useShell'
import { toastState } from './composables/useToast'

const route = useRoute()
const router = useRouter()
const surface = computed(() => route.meta.surface ?? 'service')
const surfaces = [
  ['client', '客户咨询页', '/client'],
  ['service', '客服工作台', '/workbench'],
  ['admin', '管理后台', '/overview'],
] as const
</script>

<template>
  <header class="preview-bar">
    <div class="preview-label">
      <span class="v0">V2</span><span>Minihelp <span class="muted">/ 产品预览</span></span>
    </div>
    <nav class="surface-switch" aria-label="切换产品视角">
      <button
        v-for="[key, label, path] in surfaces"
        :key="key"
        :class="{ active: surface === key }"
        :aria-pressed="surface === key"
        @click="router.push(path)"
      >
        {{ label }}
      </button>
    </nav>
    <div class="preview-options">
      <span class="demo-label">{{ route.meta.data ? '实时数据' : '演示数据' }}</span>
      <button class="text-button" @click="router.push('/migration')">页面规划 <span aria-hidden="true">↗</span></button>
      <button
        class="palette-button"
        :aria-label="`切换配色，当前${paletteName()}`"
        title="切换配色：森绿 / 纯白 / 暖纸"
        @click="cyclePalette"
      >
        <span></span><span></span><span></span>
      </button>
    </div>
  </header>

  <RouterView v-if="surface === 'client'" />
  <AppShell v-else :surface="surface">
    <RouterView />
  </AppShell>

  <div id="toast" class="toast" :class="{ show: toastState.show }" role="status" aria-live="polite">{{ toastState.message }}</div>
  <ModalHost />
  <ConfirmHost />
</template>
