# Minihelp 管理后台（Vue 3 版）

Vite + Vue 3 + TypeScript + vue-router + TanStack Query 重写的管理后台，覆盖 V2 的 8 个管理页面，全部接真实接口。
旧版 `frontend/minihelp-v2/` 保留作对照，功能核对完成前不删。

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

## 页面

| 路由 | 页面 | 主要接口 | 写操作（都需二次确认） |
|---|---|---|---|
| `#/overview` | 管理总览 | `/api/admin/overview` | — |
| `#/knowledge` | 知识中心（内容 / 录入与切块 / 候选问答 / 索引状态 / 检索自测） | `/api/kb/*` | 入库、批准或驳回候选问答、知识库作业 |
| `#/review` | 知识缺口（飞轮待审） | `/api/review/*` | 归并待处理问题、通过并发布、驳回、重试发布 |
| `#/quality` | RAG 质量（报告 / 逐题明细 / 单题试问） | `/api/rag-eval/report`、`/api/knowledge/*` | 重新评测、单题试问（付费） |
| `#/observability` | 观测与成本 | `/api/observability/overview` | 只读 |
| `#/topics` | 咨询主题 | `/api/topics/*` | 只读 |
| `#/models` | 分类器管理（九项验收 / 数据与产物 / 评测与阈值 / 错例复核 / 单句试分类） | `/api/acceptance/*` | 相关作业 |
| `#/jobs` | 作业中心 | `/api/jobs` | 启动、停止作业 |

页面内的 tab、筛选、页码都写在 URL 上（例如 `#/knowledge?tab=content&status=pending&page=2`），刷新不丢，链接可以直接分享。

## 目录结构

```
src/
├─ main.ts              应用入口：路由 + 数据请求插件
├─ router.ts            路由表与侧栏导航
├─ App.vue              侧栏 + 页面区域 + 全局确认弹窗与提示
├─ api/
│  ├─ client.ts         请求封装：超时、错误信息
│  ├─ endpoints.ts      所有接口函数
│  └─ types.ts          接口返回值类型（对照 app/api/*.py）
├─ composables/
│  ├─ useUrlState.ts    状态同步到 URL
│  ├─ useConfirm.ts     全局确认弹窗
│  ├─ useToast.ts       轻提示
│  └─ useJob.ts         作业状态轮询、启动与停止
├─ components/          通用组件：Panel、StatCard、Pill、TabBar、Pager、AppDialog、JobCard、BarList…
├─ pages/               8 个页面；知识中心和分类器管理的子分区在 knowledge/、models/ 下
├─ utils/               格式化（缺失值显示"—"，不补 0）与中文标签
└─ styles/              设计变量（沿用 V2 配色）与全局样式
```

## 约定

- **缺失不补零**：接口返回 `null` 或缺字段时显示"—"。
- **写操作先确认**：入库、审核、启动作业、调用付费模型前都会弹出确认框，说明影响。
- **超时不等于失败**：写操作超时会提示"可能已在后台完成，请先刷新核对"，不要直接重复提交。

## 待办

- [ ] 用 openapi-typescript 从 `/openapi.json` 自动生成 `api/types.ts`
- [ ] FastAPI 挂载 `dist/`（例如 `/admin`），替换旧 V2
- [ ] 客户咨询页、客服工作台（等接入电商平台时再做）
- [ ] 登录与权限（后端先补鉴权）
