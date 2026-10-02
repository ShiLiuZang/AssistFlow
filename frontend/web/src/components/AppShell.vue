<!-- V2 外壳：深色侧栏（品牌、工作区、分组导航、操作者）+ 顶栏（菜单、面包屑、状态） -->
<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import Icon from './Icon.vue'
import NavMenuModal from './NavMenuModal.vue'
import SimpleModal from './SimpleModal.vue'
import { agentSummary } from '../api/agent'
import { listReviews } from '../api/endpoints'
import { ROLE_NAMES, hasRole, session, setStaff } from '../auth/session'
import { agentLive, startAgentLive, stopAgentLive } from '../composables/useAgentLive'
import { openModal } from '../composables/useModal'

const catUrl = `${import.meta.env.BASE_URL}assets/minihelp-cat.svg`
const props = defineProps<{ surface: 'admin' | 'service' }>()
const route = useRoute()
const router = useRouter()
const staffName = computed(() => session.staff?.username ?? '未登录')
const staffRole = computed(() => (session.staff ? ROLE_NAMES[session.staff.role] : ''))
function logout() {
  stopAgentLive()
  setStaff(null)
  router.replace('/login')
}
const admin = computed(() => props.surface === 'admin')

// 知识缺口角标：待审数量（读取失败或为 0 时不显示）
const pending = useQuery({
  queryKey: ['review', 'pending-count'],
  queryFn: () => listReviews({ status: '待审', page: 1, size: 1 }),
  enabled: admin,
})
const reviewBadge = computed(() => pending.data.value?.total || '')

// 客服工作台：坐席（或管理员）登录后建立实时连接，侧栏显示排队数
const client = useQueryClient()
const agentEnabled = computed(() => !admin.value && hasRole('agent'))
const summary = useQuery({ queryKey: ['agent', 'summary'], queryFn: agentSummary, enabled: agentEnabled, refetchInterval: 60000 })
const queuedBadge = computed(() => summary.data.value?.queued || '')
watch(agentEnabled, (on) => (on ? startAgentLive(client) : stopAgentLive()), { immediate: true })
onBeforeUnmount(stopAgentLive)

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
      { path: '/workbench', label: '会话工作台', icon: 'chat', count: queuedBadge.value },
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
  if (!admin.value && route.meta.data) return agentLive.connected ? '实时推送已连接' : '实时推送连接中…'
  if (!route.meta.data) return '演示工作日 · 09 / 22'
  if (['/quality', '/observability', '/models'].includes(route.path)) return '报告与评估状态'
  if (route.path.startsWith('/topics')) return '主题归类状态'
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
const showGuide = () =>
  openModal({
    title: '页面与数据范围',
    view: SimpleModal,
    props: {
      html: '<div class="page-map"><div class="map-row"><h3>客户咨询页</h3><p>连接当前项目后端，可读取历史会话、发送问题、提交反馈及确认操作。刷新后从后端恢复会话。</p></div><div class="map-row"><h3>管理后台</h3><p>知识、审核和作业读取真实接口，操作前显示影响与确认。主题图可直接跳到类目问题明细。</p></div><div class="map-row"><h3>客服工作台</h3><p>会话工作台和工单中心连接真实接口：顾客转人工后实时进入排队，坐席接入后的回复会推送到客户咨询页。客户资料和商品页仍是演示数据。</p></div></div>',
    },
  })
const showMenu = () => openModal({ title: '页面菜单', view: NavMenuModal, props: { surface: props.surface } })
</script>

<template>
  <div class="shell" :class="{ 'admin-shell': admin }">
    <div class="rail-fill" aria-hidden="true"></div>
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
              :class="{ active: isActive || route.path.startsWith(item.path + '/') }"
              :title="item.label"
              :aria-current="isActive || route.path.startsWith(item.path + '/') ? 'page' : undefined"
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
        <span class="avatar">{{ staffName.slice(0, 1).toUpperCase() }}</span>
        <div>
          {{ staffName }}<small>{{ staffRole }}</small>
        </div>
        <button class="text-button" aria-label="退出登录" title="退出登录" @click="logout">退出</button>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <button class="btn menu-trigger" aria-label="打开页面菜单" @click="showMenu"><Icon name="book" />菜单</button>
        <div class="breadcrumb"><span class="breadcrumb-workspace">喵喵优选</span><span class="breadcrumb-divider">/</span><strong>{{ route.meta.title }}</strong></div>
        <div class="top-tools">
          <span class="small muted"><template v-if="!route.meta.data"><Icon name="clock" />{{ ' ' }}</template>{{ contextText }}</span>
          <span class="pill neutral">{{ badgeText }}</span>
          <button class="icon-btn" aria-label="操作说明" @click="showGuide"><Icon name="info" /></button>
        </div>
      </header>
      <slot />
    </main>
  </div>
</template>
