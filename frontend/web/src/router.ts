// 路由：URL 和页面的对应关系。页面内的 tab / 筛选 / 页码放在 query 里（见 composables/useUrlState.ts）
import { createRouter, createWebHashHistory } from 'vue-router'

export const navItems = [
  { group: '总览', path: '/overview', label: '管理总览' },
  { group: '知识与质量', path: '/knowledge', label: '知识中心' },
  { group: '知识与质量', path: '/review', label: '知识缺口' },
  { group: '知识与质量', path: '/quality', label: 'RAG 质量' },
  { group: '运营与模型', path: '/observability', label: '观测与成本' },
  { group: '运营与模型', path: '/topics', label: '咨询主题' },
  { group: '运营与模型', path: '/models', label: '分类器管理' },
  { group: '运营与模型', path: '/jobs', label: '作业中心' },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', component: () => import('./pages/OverviewPage.vue'), meta: { title: '管理总览' } },
    { path: '/knowledge', component: () => import('./pages/KnowledgePage.vue'), meta: { title: '知识中心' } },
    { path: '/review', component: () => import('./pages/ReviewPage.vue'), meta: { title: '知识缺口' } },
    { path: '/quality', component: () => import('./pages/QualityPage.vue'), meta: { title: 'RAG 质量' } },
    { path: '/observability', component: () => import('./pages/ObservabilityPage.vue'), meta: { title: '观测与成本' } },
    { path: '/topics', component: () => import('./pages/TopicsPage.vue'), meta: { title: '咨询主题' } },
    { path: '/models', component: () => import('./pages/ModelsPage.vue'), meta: { title: '分类器管理' } },
    { path: '/jobs', component: () => import('./pages/JobsPage.vue'), meta: { title: '作业中心' } },
    { path: '/:pathMatch(.*)*', redirect: '/overview' },
  ],
})

router.afterEach((to) => {
  document.title = `${(to.meta.title as string) ?? '管理后台'} · Minihelp`
})
