// 路由：与 V2 相同的 hash 地址（#/overview、#/workbench、#/client …）。
// meta.surface 决定外壳：admin = 管理后台，service = 客服工作台，client = 客户咨询页
import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

type Surface = 'admin' | 'service' | 'client'
declare module 'vue-router' {
  interface RouteMeta {
    title: string
    surface: Surface
    /** 读取真实接口的管理页（显示"实时接口"来源条与读数时间） */
    data?: boolean
  }
}

const page = (path: string, title: string, surface: Surface, component: RouteRecordRaw['component'], data = false) =>
  ({ path, component, meta: { title, surface, data } }) as RouteRecordRaw

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    // 管理后台：真实接口
    page('/overview', '管理总览', 'admin', () => import('./pages/OverviewPage.vue'), true),
    page('/knowledge', '知识中心', 'admin', () => import('./pages/KnowledgePage.vue'), true),
    page('/review', '知识缺口', 'admin', () => import('./pages/ReviewPage.vue'), true),
    page('/quality', 'RAG 质量', 'admin', () => import('./pages/QualityPage.vue'), true),
    page('/observability', '观测与成本', 'admin', () => import('./pages/ObservabilityPage.vue'), true),
    page('/topics', '咨询主题', 'admin', () => import('./pages/TopicsPage.vue'), true),
    page('/topics/questions', '类目问题明细', 'admin', () => import('./pages/TopicsPage.vue'), true),
    page('/models', '分类器管理', 'admin', () => import('./pages/ModelsPage.vue'), true),
    page('/jobs', '作业中心', 'admin', () => import('./pages/JobsPage.vue'), true),
    // 管理后台：演示页
    page('/migration', '原功能对照', 'admin', () => import('./pages/demo/MigrationPage.vue')),
    page('/settings', '设置与权限', 'admin', () => import('./pages/demo/SettingsPage.vue')),
    // 客服工作台：演示页
    page('/workbench', '会话工作台', 'service', () => import('./pages/demo/WorkbenchPage.vue')),
    page('/tickets', '工单中心', 'service', () => import('./pages/demo/TicketsPage.vue')),
    page('/customers', '客户资料', 'service', () => import('./pages/demo/CustomersPage.vue')),
    page('/products', '商品与订单', 'service', () => import('./pages/demo/ProductsPage.vue')),
    // 客户咨询页
    page('/client', '客户咨询页', 'client', () => import('./pages/ClientPage.vue'), true),
    { path: '/:pathMatch(.*)*', redirect: '/workbench' },
  ],
  scrollBehavior(to, from, saved) {
    return saved || (to.path !== from.path ? { top: 0 } : undefined)
  },
})

router.afterEach((to) => {
  document.title = `${to.meta.title ?? 'Minihelp'} · Minihelp V2`
})
