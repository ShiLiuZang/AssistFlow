// 路由：URL 和页面的对应关系。
// 以后 tab、筛选、分页也可以放进 URL 的 query 里（例如 /knowledge?tab=index），刷新不丢
import { createRouter, createWebHashHistory } from 'vue-router'
import KnowledgePage from './pages/KnowledgePage.vue'

export const router = createRouter({
  // hash 模式（URL 里带 #），部署时后端不需要额外配置
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/knowledge' },
    { path: '/knowledge', component: KnowledgePage, meta: { title: '知识中心' } },
  ],
})
