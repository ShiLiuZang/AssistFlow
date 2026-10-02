<!-- 窄屏页面菜单（对应 V2 的 nav-menu） -->
<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import Icon from './Icon.vue'
import { closeModal } from '../composables/useModal'

const props = defineProps<{ surface: 'admin' | 'service' }>()
const route = useRoute()
const router = useRouter()
const entries: Record<string, [string, string]> = {
  overview: ['管理总览', 'chart'],
  knowledge: ['知识库', 'book'],
  review: ['知识缺口', 'search'],
  quality: ['RAG 质量', 'shield'],
  observability: ['观测与成本', 'chart'],
  topics: ['咨询主题', 'chat'],
  models: ['分类器管理', 'spark'],
  jobs: ['作业中心', 'clock'],
  settings: ['设置与接入', 'settings'],
  migration: ['原功能对照', 'file'],
  workbench: ['客服工作台', 'headset'],
  tickets: ['工单中心', 'ticket'],
  customers: ['客户资料', 'users'],
  products: ['商品与订单', 'box'],
}
const menu =
  props.surface === 'admin'
    ? ['overview', 'knowledge', 'review', 'quality', 'observability', 'topics', 'models', 'jobs', 'settings', 'migration', 'workbench']
    : ['workbench', 'tickets', 'customers', 'products', 'overview', 'settings']
function open(page: string) {
  closeModal()
  router.push(`/${page}`)
}
</script>

<template>
  <div class="modal-body">
    <nav class="mobile-menu-list" aria-label="页面入口">
      <button v-for="page in menu" :key="page" :class="{ active: route.path === `/${page}` }" @click="open(page)">
        <Icon :name="entries[page][1]" />{{ entries[page][0] }}
      </button>
    </nav>
  </div>
  <div class="modal-foot"><button class="btn" @click="closeModal">知道了</button></div>
</template>
