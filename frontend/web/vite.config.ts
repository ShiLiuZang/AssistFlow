import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 开发时把 /api 请求转发给 FastAPI，前后端看起来是同一个域名，不用处理跨域
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
