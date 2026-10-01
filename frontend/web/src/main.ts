// 应用入口：创建 Vue 应用，装上路由和数据请求插件，然后挂载到 index.html 的 #app
import { createApp } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import { router } from './router'
import './styles/tokens.css'
import './styles/base.css'

// QueryClient 负责缓存所有接口数据。
// 旧 V2 里手写的 ui.cache / epoch 防竞态，现在都由它管。
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1, // 失败自动重试 1 次
      refetchOnWindowFocus: false, // 切回窗口时不自动刷新，避免后台读数突然变化
    },
  },
})

createApp(App).use(router).use(VueQueryPlugin, { queryClient }).mount('#app')
