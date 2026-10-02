# Minihelp 前端（Vue 3 版）

用 Vite + Vue 3 + TypeScript + vue-router + TanStack Query，把 V2 原型（`frontend/minihelp-v2/`）**1:1 迁移**到 Vue：视觉、交互、文案与 V2 一致，直接复用 V2 的 CSS 和页面结构，只把原来手写的字符串拼接换成组件。
迁移时顺手修了 V2 的几个问题：页面状态写进 URL、修掉 Pill 的双重转义、跨页面跳转能落到正确的子页。
V2 保留作对照。

## 运行

需要 Node.js 20.19 以上（推荐 22）。

```powershell
cd frontend\web
npm install
npm run dev          # http://localhost:5173
```

另开终端启动后端：`uv run uvicorn app.main:app --port 8000`。开发服务器会把 `/api` 转发到 8000 端口（见 `vite.config.ts`）。

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器，改代码自动刷新 |
| `npm run typecheck` | TypeScript 类型检查 |
| `npm run build` | 类型检查 + 打包到 `dist/` |

## 三种视角

顶部预览栏切换，与 V2 相同。

### 管理后台（真实接口）

| 路由 | 页面 | 主要接口 | 写操作（都需核对确认） |
|---|---|---|---|
| `#/overview` | 管理总览 | `/api/admin/overview` | — |
| `#/knowledge` | 知识中心（内容 / 录入与切块 / 对话挖知识 / 索引状态 / 检索自测） | `/api/kb/*` | 入库、批准或驳回候选问答、补齐向量 |
| `#/review` | 知识缺口（飞轮待审） | `/api/review/*` | 归并待处理问题、核准发布、驳回、重试发布 |
| `#/quality` | RAG 质量（检索与生成评估 / 逐题结果 / 固定题集 / 单题体验） | `/api/rag-eval/report`、`/api/knowledge/*` | 运行固定题集评估、单题体验（调用模型） |
| `#/observability` | 观测与成本（意图消耗 / 评估趋势 / 置信度校准） | `/api/observability/overview` | 只读 |
| `#/topics` | 咨询主题 | `/api/topics/*` | 只读 |
| `#/models` | 分类器管理（九项验收 / 数据与产物 / 评测与阈值 / 错例复核 / 单句试分类） | `/api/acceptance/*` | 重跑相关作业 |
| `#/jobs` | 作业中心 | `/api/jobs` | 启动、停止作业 |
| `#/migration` | 原功能对照 | — | 演示 |
| `#/settings` | 设置与权限 | — | 演示 |

### 客服工作台与客户咨询页（演示数据）

`#/workbench` 会话工作台、`#/tickets` 工单中心、`#/customers` 客户资料、`#/products` 商品与订单、`#/client` 客户咨询页。
数据在 `src/demo/store.ts`，只存在内存里，刷新后重置，不调用任何接口。三个页面共用同一份数据：在工作台接管并回复，客户咨询页能看到；客户提交退货申请，工单中心能领取处理。

页面内的子页、筛选、页码都写在 URL 上（例如 `#/models?tab=evaluation`、`#/review?status=all&page=2`），刷新不丢，链接可以直接分享。

## 目录结构

```
src/
├─ main.ts              应用入口：按 V2 顺序引入样式，挂载路由与数据请求
├─ router.ts            路由表；meta.surface 决定用哪种外壳
├─ App.vue              顶部预览栏 + 外壳 + 全局弹窗与提示
├─ api/                 请求封装、接口函数、返回值类型（对照 app/api/*.py）
├─ composables/
│  ├─ useUrlState.ts    页面状态同步到 URL（同一事件的多次修改合并为一次）
│  ├─ useAdminActions.ts 写操作的"读取 → 核对 → 执行 → 结果"流程
│  ├─ useModal.ts       全局弹窗（对应 V2 的 <dialog id="modal">）
│  └─ useToast.ts …     轻提示、读数时间、配色切换
├─ components/          外壳与通用组件：AppShell、DataPage、VPanel、VStat、VTable、StatusPill…
├─ pages/               管理页；子分区在 knowledge/、workflows/、reports/、classification/、models/、demo/ 下
├─ demo/                演示数据与演示页共用的弹窗（订单、工单、知识）
└─ styles/v2/           V2 原样式（不改动）
```

## 约定

- **缺失不补零**：接口返回 `null` 或缺字段时显示"—"。
- **写操作先核对**：入库、审核、启动作业、调用付费模型前，先读取最新状态并列出影响，确认后才执行。
- **超时不等于失败**：写操作超时会提示"可能已在后台完成，请先刷新核对"，不要直接重复提交。

## 待办

- [ ] 用 openapi-typescript 从 `/openapi.json` 自动生成 `api/types.ts`
- [ ] FastAPI 挂载 `dist/`（例如 `/admin`），替换旧 V2
- [ ] 客服工作台、客户咨询页接入真实会话与电商平台
- [ ] 登录与权限（后端先补鉴权）
