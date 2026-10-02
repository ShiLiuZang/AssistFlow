// 应用入口：创建 Vue 应用，装上路由和数据请求插件，然后挂载到 index.html 的 #app
import { createApp } from 'vue'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { queryClient } from './queryClient'
import App from './App.vue'
import { router } from './router'
// V2 样式原样复用，顺序与 V2 index.html 一致
import './styles/v2/prototype.css'
import './styles/v2/admin-panels.css'
import './styles/v2/service-panels.css'
import './styles/v2/admin-data.css'
import './styles/v2/admin-workflows.css'
import './styles/v2/admin-reports.css'
import './styles/v2/admin-classification.css'
import './styles/fixes.css'


createApp(App).use(router).use(VueQueryPlugin, { queryClient }).mount('#app')
