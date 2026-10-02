<!-- V2 外壳：深色侧栏（品牌、工作区、分组导航、操作者）+ 顶栏（菜单、面包屑、状态） -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import Icon from './Icon.vue'
import NavMenuModal from './NavMenuModal.vue'
import SimpleModal from './SimpleModal.vue'
import { listReviews } from '../api/endpoints'
import { openModal } from '../composables/useModal'
import { queuedCount } from '../demo/store'

const catUrl = `${import.meta.env.BASE_URL}assets/minihelp-cat.svg`
const props = defineProps<{ surface: 'admin' | 'service' }>()
const route = useRoute()
const admin = computed(() => props.surface === 'admin')

// 知识缺口角标：待审数量（读取失败或为 0 时不显示）
const pending = useQuery({
  queryKey: ['review', 'pending-count'],
  queryFn: () => listReviews({ status: '待审', page: 1, size: 1 }),
  enabled: admin,
})
const reviewBadge = computed(() => pending.data.value?.total || '')

type NavItem = { path: string; label: string; icon: string; count?: string | number }
const adminGroups = computed<{ label?: string; items: NavItem[]; bottom?: boolean }[]>(() => [
  { items: [{ path: '/overview', label: '管理总览', icon: 'chart' }] },
  {
    label: '知识与质量',
    items: [
      { path: '/knowledge', label: '知识中心', icon: 'book' },
      { path: '/review', label: '知识缺口', icon: 'search', count: reviewBadge.value },
      { path: '/quality', label: 'RAG 质量', icon: 'shield' },
    ],
  },
  {
    label: '运营与模型',
    items: [
      { path: '/observability', label: '观测与成本', icon: 'chart' },
      { path: '/topics', label: '咨询主题', icon: 'chat' },
      { path: '/models', label: '分类器管理', icon: 'spark' },
      { path: '/jobs', label: '作业中心', icon: 'clock' },
    ],
  },
  {
    bottom: true,
    items: [
      { path: '/migration', label: '原功能对照', icon: 'file' },
      { path: '/settings', label: '设置与权限', icon: 'settings' },
    ],
  },
])
const serviceGroups = computed<{ label?: string; items: NavItem[]; bottom?: boolean }[]>(() => [
  {
    label: '服务工作区',
    items: [
      { path: '/workbench', label: '会话工作台', icon: 'chat', count: queuedCount.value },
      { path: '/tickets', label: '工单中心', icon: 'ticket' },
      { path: '/customers', label: '客户资料', icon: 'users' },
      { path: '/products', label: '商品与订单', icon: 'box' },
    ],
  },
  {
    label: '运营管理',
    items: [
      { path: '/overview', label: '进入管理后台', icon: 'chart' },
      { path: '/migration', label: '原功能对照', icon: 'file' },
    ],
  },
])
const groups = computed(() => (admin.value ? adminGroups.value : serviceGroups.value))

const contextText = computed(() => {
  if (!route.meta.data) return '演示工作日 · 09 / 22'
  if (['/quality', '/observability', '/models'].includes(route.path)) return '报告与评估状态'
  if (route.path === '/topics') return '主题归类状态'
  return '库存与运行状态'
})
const badgeText = computed(() => (route.meta.data ? (route.path === '/observability' ? '实时数据 · 只读' : '实时数据') : admin.value ? '数据演示' : '演示接待'))

const showWorkspace = () =>
  openModal({
    title: '当前工作区',
    view: SimpleModal,
    props: {
      html: '<div class="row"><span class="avatar green">喵</span><div><h3>喵喵优选</h3><p class="muted">独立店铺 · Web 咨询渠道</p></div></div><p style="margin-top:20px">首版以单组织、单工作区为产品边界。成员管理和渠道接入将在设置页中配置。</p>',
    },
  })
const showProfile = () =>
  openModal({
    title: '周小雨 · 演示账号',
    view: SimpleModal,
    props: {
      html: '<div class="notice">这是交互原型，没有登录会话和真实权限控制。</div><p>规划角色：管理员、主管、客服。生产版根据角色区分知识发布、成员管理、客服接管和工单处理权限。</p>',
    },
  })
const showGuide = () =>
  openModal({
    title: '这样体验本轮原型',
    view: SimpleModal,
    props: {
      html: '<div class="page-map"><div class="map-row"><h3>01 · 接待客户</h3><p>在工作台接管林女士的会话，输入回复，然后切换到客户咨询页查看。</p></div><div class="map-row"><h3>02 · 跟进售后</h3><p>在客户页提交退货申请，再到工单中心领取和记录处理结果。</p></div><div class="map-row"><h3>03 · 更新知识</h3><p>在知识库添加草稿、提交审核、发布，查看状态和数量变化。</p></div></div><p class="field-hint">右上角色视角用于预览；正式版会按登录身份展示对应入口。刷新页面会重置数据。</p>',
    },
  })
const showMenu = () => openModal({ title: '页面菜单', view: NavMenuModal, props: { surface: props.surface } })
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><img :src="catUrl" alt="" /><span>Minihelp</span></div>
      <button class="workspace-selector" @click="showWorkspace">
        <span class="shop-letter">喵</span><span>喵喵优选</span><Icon name="down" />
      </button>
      <template v-for="(g, i) in groups" :key="i">
        <p v-if="g.label" class="nav-label">{{ g.label }}</p>
        <nav class="nav-group" :class="{ 'nav-bottom': g.bottom }" :aria-label="g.label ?? g.items[0].label">
          <RouterLink
            v-for="item in g.items"
            :key="item.path"
            v-slot="{ navigate, isActive }"
            :to="item.path"
            custom
          >
            <button
              class="nav-item"
              :class="{ active: isActive }"
              :title="item.label"
              :aria-current="isActive ? 'page' : undefined"
              @click="navigate"
            >
              <Icon :name="item.icon" /><span class="nav-name">{{ item.label }}</span>
              <span v-if="item.count" class="nav-count">{{ item.count }}</span>
            </button>
          </RouterLink>
        </nav>
      </template>
      <div class="rail-note">每一次对话，<br />都值得被认真回应。</div>
      <div class="operator">
        <span class="avatar">周</span>
        <div>
          周小雨<small>{{ admin ? '管理员' : '客服' }} · 演示视角</small>
        </div>
        <button class="icon-btn" aria-label="当前账号" @click="showProfile"><Icon name="down" /></button>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <button class="btn menu-trigger" aria-label="打开页面菜单" @click="showMenu"><Icon name="book" />菜单</button>
        <div class="breadcrumb">喵喵优选<span>/</span><strong>{{ route.meta.title }}</strong></div>
        <div class="top-tools">
          <span class="small muted"><template v-if="!route.meta.data"><Icon name="clock" /> </template>{{ contextText }}</span>
          <span class="pill neutral">{{ badgeText }}</span>
          <button class="icon-btn" aria-label="操作说明" @click="showGuide"><Icon name="info" /></button>
        </div>
      </header>
      <slot />
    </main>
  </div>
</template>
