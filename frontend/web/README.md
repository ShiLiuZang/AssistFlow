# Minihelp 管理后台（Vue 3 版）

用 Vite + Vue 3 + TypeScript 重写 V2 管理后台。旧版 `frontend/minihelp-v2/` 保留作对照，功能对齐前不删。

## 运行

需要 Node.js 20.19 以上（推荐 22）。

```powershell
cd frontend/web
npm install          # 第一次运行时安装依赖
npm run dev          # 启动开发服务器
```

另开一个终端启动后端（`uv run uvicorn app.main:app --port 8000`），然后打开 http://localhost:5173 。
开发服务器会把 `/api` 请求转发给 8000 端口，见 `vite.config.ts`。

其他命令：`npm run typecheck`（类型检查）、`npm run build`（打包到 `dist/`）。

## 文件地图（按阅读顺序）

| 文件 | 作用 | 学到的 Vue 概念 |
|---|---|---|
| `index.html` | 页面外壳，只有一个 `#app` | 应用挂载点 |
| `src/main.ts` | 创建应用，装路由和数据请求插件 | `createApp`、插件 `use()` |
| `src/router.ts` | URL 和页面的对应关系 | 路由、`redirect` |
| `src/App.vue` | 左侧导航 + 页面区域 | 单文件组件、`v-for`、`RouterLink`、`RouterView`、`scoped` 样式 |
| `src/api/client.ts` | 统一请求：超时、错误信息 | （纯 TypeScript） |
| `src/api/kb.ts` | 知识库接口和返回值类型 | TypeScript 接口类型 |
| `src/components/StatCard.vue` | 统计卡片组件 | `defineProps`、`computed`、`v-if`、`:class` |
| `src/pages/KnowledgePage.vue` | 知识中心页面 | `useQuery`、`v-if/v-else-if/v-else`、事件 `@click`、属性绑定 `:value` |

## 小实验（自己动手改一改）

1. 在 `StatCard.vue` 里把 `tone === 'warn'` 时的颜色改成红色，看"双写核对"的变化。
2. 关掉后端再刷新页面，看错误状态怎么显示；再打开后端点"重新读取"。
3. 在 `KnowledgePage.vue` 加第 7 张卡片，显示 `data.chunks.by_content_type` 里的类型数量。
4. 在 `router.ts` 加一个新页面路由，在 `App.vue` 的 `navItems` 加一项导航。

## 迁移进度

- [x] 脚手架、路由、数据请求层、设计变量
- [x] 知识中心：库存统计卡片
- [ ] 知识中心：知识内容表格、筛选、分页（状态同步到 URL）
- [ ] 知识中心：录入与切块、检索自测
- [ ] 其余 7 个管理页面
- [ ] 用 openapi-typescript 从后端自动生成接口类型
- [ ] FastAPI 挂载 `dist/`，替换旧 V2
