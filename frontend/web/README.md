# Minihelp 前端（Vue 3 版）

用 Vite + Vue 3 + TypeScript + vue-router + TanStack Query 承接 V2 原型（`frontend/minihelp-v2/`），保留色板与导航，管理页采用紧凑统计、表格和图表；客户聊天接入本项目后端。
迁移时顺手修了 V2 的几个问题：页面状态写进 URL、修掉 Pill 的双重转义、跨页面跳转能落到正确的子页。
V2 保留作对照。

## 运行

需要 Node.js 22.6 以上（前端测试直接运行 TypeScript 源文件）。

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
| `npm run build` | 类型检查 + 打包到 `dist/`（FastAPI 在 `/` 托管） |
| `npm test` | 前端单元测试 |

## 三种视角

顶部预览栏切换，与 V2 相同。

### 管理后台（真实接口）

| 路由 | 页面 | 主要接口 | 写操作（都需核对确认） |
|---|---|---|---|
| `#/overview` | 管理总览 | `/api/admin/overview` | — |
| `#/knowledge` | 知识中心（内容 / 录入与切块 / 候选问答 / 索引状态 / 检索自测） | `/api/kb/*` | 入库、挖掘、批准或驳回候选问答、补齐向量 |
| `#/review` | 知识缺口（飞轮待审） | `/api/review/*` | 归并待处理问题、核准发布、驳回、重试发布 |
| `#/quality` | RAG 质量（检索与生成评估 / 逐题结果 / 固定题集 / 单题体验） | `/api/rag-eval/report`、`/api/knowledge/*` | 运行固定题集评估、单题体验（调用模型） |
| `#/observability` | 观测与成本（意图消耗 / 评估趋势 / 置信度校准） | `/api/observability/overview` | 只读 |
| `#/topics` | 咨询主题 | `/api/topics/*` | 只读 |
| `#/topics/questions?label=物流` | 所选类目问题明细（独立页面） | `/api/topics/*` | 只读 |
| `#/models` | 分类器管理（九项验收 / 数据与产物 / 评测与阈值 / 错例复核 / 单句试分类） | `/api/acceptance/*` | 重跑相关作业 |
| `#/jobs` | 作业中心 | `/api/jobs` | 启动、停止作业 |
| `#/migration` | 原功能对照 | — | 演示 |
| `#/settings` | 设置与权限 | — | 演示 |

### 客户咨询页（真实接口）

`#/client` 通过 `/api/graph-chat` 接收事件流，读取会话历史与待确认操作，通过 `/api/feedback` 提交反馈。支持工单确认、订单选择、连接中断后的重新读取；失败时不会以演示回复代替。顾客身份来自令牌：嵌入商城时通过地址参数 `#/client?token=…` 或 `postMessage({ type: 'assistflow:customer-token', token })` 传入；开发模式（`AUTH_DEV_MODE=true`）下可在侧栏输入顾客 ID 模拟登录。管理后台与客服工作台需要员工登录（`#/login`）。

### 客服工作台（演示数据）

`#/workbench`、`#/tickets`、`#/customers`、`#/products` 仍使用 `src/demo/store.ts` 的内存演示数据，与真实客户聊天分开。刷新会重置，不代表真实客服接管已经接通。

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
- **管理写操作先核对**：入库、审核、启动作业、评估前先读取最新状态并列出影响。聊天点击发送即调用模型；工单提交另需确认。
- **超时不等于失败**：写操作超时会提示"可能已在后台完成，请先刷新核对"，不要直接重复提交。

## 待办

- [ ] 用 openapi-typescript 从 `/openapi.json` 自动生成 `api/types.ts`
- [x] FastAPI 在 `/` 托管 `dist/`，旧静态页已删除
- [ ] 客服工作台与电商平台集成（客户聊天已连接本项目 API）
- [x] 登录与权限：员工登录、按角色提示写操作权限，令牌保存在 sessionStorage

## 对话挖知识与飞轮

- 知识中心 → 候选问答 → **从对话挖掘候选**，对应 `python -m scripts.tasks kb-mine`。读取最近 20 个有助手回复的会话，每个最多 40 条消息、12,000 字符，过滤订单号、电话等标识后复用 `mine_dialogue`。仅接受可信材料原文，写入候选暂存区，人工采纳后才能进入正式知识库。
- 已有候选的相同会话批次跳过，同一候选不会重复新增。没有产生候选的会话再次运行会重新尝试模型调用；批次不作为全量历史挖掘进度。
- 知识缺口 → **对话快照 / 问题池 / 待归并** 显示 `/api/review/stats` 的真实计数。负反馈或满足采集条件的拒答先进入问题池，点击归并后才产生待审项；历史会话数量不等于待审数量。
- 当前轮次的具体任务和验收边界见 [docs/web-v2-integration-plan.md](../../docs/web-v2-integration-plan.md)。
