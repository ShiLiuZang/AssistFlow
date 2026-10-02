# 阶段 2：人工坐席闭环 设计说明

目标：AI 答不了或用户要求时，会话真正转到人工坐席；坐席在工作台实时接待、回复、建工单；人工回复回流到知识缺口队列。

## 会话状态

会话本身不加状态字段，状态由“转人工记录”（`handoffs` 表）推导：

| 状态 | 含义 | AI 是否回复 |
|---|---|---|
| 没有未结束的转人工记录 | AI 接待 | 是 |
| `queued` | 排队中，等坐席接入 | 否，顾客消息直接进坐席队列 |
| `active` | 人工接待，`assignee` 为接待坐席 | 否 |
| `closed` / `cancelled` | 人工结束或顾客取消排队，恢复 AI 接待 | 是 |

同一会话同时最多一条 `queued/active` 记录；转人工请求是幂等的。

## 数据表（迁移 `c120001`）

- `handoffs`：会话、顾客、状态、原因（`human` 用户要求、`complaint` 投诉、`customer_request` 点击按钮、`staff_takeover` 坐席主动接管）、交接卡片 JSON、接待坐席、各时间点、结束人、是否已回流。
- `messages` 新增 `author` 列和四种角色：`handoff_user`（人工期间的顾客消息）、`staff`（坐席回复）、`staff_note`（内部备注，顾客不可见）、`handoff_event`（接入、转交、结束等系统提示）。这些角色不进入 LangGraph 历史，`persist_graph_messages` 和一致性校验只看 `user/assistant/tool`，所以图状态不受影响。
- `tickets` 新增顾客、标题、优先级、负责人、来源（顾客确认 / 坐席创建）、更新时间；新增 `ticket_events` 记录每次状态流转。

## 交接卡片

转人工时生成，内容：AI 摘要（滚动摘要加最近几轮对话）、本轮检索到的证据（前 3 条）、订单信息、用户情绪（关键词规则，标注为规则判断）、识别出的意图。坐席接入前就能看到全貌，不用翻聊天记录。

## 转人工入口

1. 图里的 `human` 和 `complaint` 节点：创建排队记录，回复“已为您转接人工客服，前面还有 N 位”。数据库不可用时退回原来的引导话术。
2. 客户咨询页的“转人工”按钮：`POST /api/conversations/{id}/handoff`。
3. 坐席在工作台主动接管 AI 接待中的会话。

## 接口

顾客（顾客令牌）：

- `POST /api/graph-chat`：会话处于排队或人工接待时，消息不经过 AI，存为 `handoff_user` 并推送给坐席，返回 `handoff` 事件。
- `GET /api/conversations/{id}/handoff`、`POST .../handoff`、`POST .../handoff/cancel`
- `GET /api/conversations/{id}/events`：SSE，推送坐席回复和状态变化。
- `GET /api/conversations/{id}/messages`：增加坐席回复和系统提示，不含内部备注。

坐席（员工令牌，坐席或管理员）：`/api/agent/...`

- `GET conversations?view=queued|mine|active|ai`，`GET conversations/{id}`
- `POST conversations/{id}/accept|messages|transfer|close`
- `GET/POST tickets`，`GET tickets/{no}`，`POST tickets/{no}/status`
- `GET stream`：SSE，推送队列变化和顾客新消息。

## 实时推送

选 SSE 而不是 WebSocket：推送是单向的，坐席和顾客的操作都走普通 REST 请求；SSE 能用 `Authorization` 头带令牌（前端用 fetch 读流），不用把令牌放进 URL，也不需要额外协议。进程内用 `asyncio.Queue` 做发布订阅，每 15 秒一次心跳。**只支持单实例**，阶段 4 换成 Redis Pub/Sub。

## 工单

`app/core/tickets.py` 定义 `TicketBackend` 接口和本地数据库实现，后续可替换为外部工单系统。状态流转：

```
待处理 → 处理中 / 已关闭
处理中 → 已解决 / 待处理 / 已关闭
已解决 → 处理中（重开）/ 已关闭
已关闭（终态）
```

顾客在会话中确认的工单（原有幂等逻辑不变）也会写入一条“顾客确认创建”记录。

## 知识回流

人工接待结束时，把“顾客问题 → 坐席回复”配对（脱敏后）写入问题池，来源 `human_handoff`。现有的归并作业把它们并入知识缺口队列，并优先用坐席回复作为建议答案。仍然要审核员对照可信材料核准后才能发布：坐席回复只是草稿，不直接进知识库，这与项目原有“答案必须来自可信材料原文”的原则一致。

## 不在本阶段

- 多实例下的推送与锁（阶段 4）。
- 坐席排班、自动分配、并发上限、满意度评价。
- 人工期间的对话不会写回 AI 的上下文：恢复 AI 接待后，AI 只看到转人工之前的历史。
- 客户资料、商品与订单页仍是演示数据。
