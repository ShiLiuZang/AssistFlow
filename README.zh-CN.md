# 智能客服系统

> 面向电商场景的企业级智能客服平台 · 对话管理、知识问答、业务办理与质量运营

[English](./README.md) | 简体中文

这是一个采用 **FastAPI + LangGraph + MySQL + Milvus** 技术栈构建的企业级电商智能客服系统。系统支持自然语言对话、知识库检索、订单查询、工单处理，并提供完整的知识运营和质量监控能力。

## 鉴权

API 使用两类 `Authorization: Bearer <token>` 凭据：

- **访客令牌**：公开的 `POST /api/auth/visitor` 由服务端生成匿名 `user_id`、HMAC-SHA256 签名令牌和 Unix 秒过期时间 `expires_at`。聊天、会话、待处理操作、确认、选单、反馈及信息抽取接口均需要访客令牌。兼容请求体/查询参数中可选的 `user_id`，与令牌身份不一致时返回 403；缺失、无效或过期令牌返回 401，并带 `WWW-Authenticate: Bearer`。
- **管理员令牌**：将 `ADMIN_TOKEN` 配置为私密随机值，知识库、审核、任务、观测、验收、主题及管理 API 必须携带相同令牌。未配置时返回 503「未配置 ADMIN_TOKEN」；缺失或错误令牌返回 401。

将 `AUTH_SECRET` 配置为私密随机签名密钥，可设置 `VISITOR_TOKEN_TTL_DAYS`（默认 30 天）。`AUTH_SECRET` 为空时，启动会生成仅保存在当前进程的随机密钥，并告警说明重启后访客令牌失效，不记录密钥。多进程服务应配置相同密钥；更换密钥也会使已有访客令牌失效。

聊天页将访客凭据保存在 localStorage，收到 401 后自动换令牌并重试一次；新匿名身份无法访问旧身份的会话。管理页面收到 401/503 时提示输入 `ADMIN_TOKEN`、保存并重试一次。HTML 页面、`/static`、`/api/health` 和访客签发接口保持公开；页面输入令牌不能代替服务端的 `ADMIN_TOKEN` 配置。

访客令牌是演示用的匿名身份，不代表经过验证的真实顾客账号。生产环境应由上游平台签发身份并由服务端验证。HTTP 脚本调用顾客 API 前应先获取访客令牌；调用管理 API 时应读取 `ADMIN_TOKEN` 环境变量。

## ✨ 核心特性

### 🤖 智能对话
- **流式响应**，基于 SSE 协议实时推送
- **多轮上下文管理**，支持对话摘要
- **意图识别**与智能路由（9 类意图）
- **指代消解**，跨轮次实体追踪

### 📚 知识问答（RAG）
- **向量检索**，基于 Milvus + 可选重排序
- **证据充分性评估**，置信度评分
- **问题拆分**与多路检索
- **知识审核流程**，暂存与审批机制

### 🛠️ 业务工具
- **订单查询**，用户权限隔离
- **工单创建**，确认流程
- **MCP 集成**，外部服务（物流、售后）
- **工具审计**，完整调用历史与重放

### 📊 质量与可观测性
- **低置信度追踪**，反馈收集
- **执行追踪**，可选 Langfuse 集成
- **模型用量报告**，按意图口径统计
- **17 类主题分类器**，支持微调

### 🔧 开发体验
- **完整中文注释**，覆盖所有模块
- **本地验证脚本**，覆盖部分关键流程
- **数据库迁移**，使用 Alembic
- **一键启动**，Docker Compose 配置

---

## 🏗️ 系统架构

```
┌─────────────┐
│  用户/管理员 │
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────┐
│            FastAPI Web 层                    │
│  路由：聊天、知识、审核、观测                │
└──────┬──────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────┐
│         LangGraph 对话流程编排               │
│  节点：意图→检索→工具→回答→摘要            │
└─┬──────┬──────┬──────┬─────────────────────┘
  │      │      │      │
  │      │      │      └─→ [订单/工单/MCP工具]
  │      │      └────────→ [Milvus 向量检索]
  │      └───────────────→ [LLM 模型服务]
  └──────────────────────→ [MySQL 业务数据]
```

### 技术栈

| 层级 | 技术选型 |
|------|---------|
| **Web 框架** | FastAPI + Uvicorn |
| **对话编排** | LangGraph + LangChain |
| **数据存储** | MySQL (SQLAlchemy + Alembic) + SQLite (对话检查点) |
| **向量检索** | Milvus + OpenAI 兼容 Embedding API |
| **LLM 调用** | OpenAI 兼容 Chat API（支持思考模式） |
| **工具集成** | MCP (Model Context Protocol) |
| **可观测性** | 本地追踪 + 可选 Langfuse |
| **主题分类** | PyTorch + Transformers + ONNX Runtime |
| **前端** | 原生 HTML/CSS/JavaScript |

---

## 📁 项目结构

```
智能客服/
├── app/
│   ├── api/                  # FastAPI 路由（15 个模块）
│   │   ├── graph_chat.py     # LangGraph 流式聊天
│   │   ├── conversations.py  # 会话历史
│   │   ├── knowledge.py      # 知识检索与 RAG 评测
│   │   ├── observability.py  # 执行追踪与用量
│   │   ├── feedback.py       # 用户反馈
│   │   ├── review.py         # 知识审核队列
│   │   ├── topics.py         # 主题分类
│   │   ├── acceptance.py     # 分类器验收
│   │   └── ...
│   ├── core/                 # 业务逻辑（28 个模块）
│   │   ├── llm.py            # LLM 客户端工厂
│   │   ├── embeddings.py     # 文本向量化
│   │   ├── retrieval.py      # 统一检索接口
│   │   ├── rerank.py         # 可选重排序
│   │   ├── intent.py         # 意图分类
│   │   ├── evidence.py       # 证据评估
│   │   ├── confidence.py     # 置信度评分
│   │   ├── coref.py          # 指代消解
│   │   ├── summarizer.py     # 滚动对话摘要
│   │   ├── observability.py  # 追踪与 token 用量
│   │   └── ...
│   ├── graph/                # LangGraph 实现（8 个模块）
│   │   ├── state.py          # 对话状态模式
│   │   ├── nodes.py          # 节点实现
│   │   ├── routing.py        # 条件路由
│   │   ├── build.py          # 图组装
│   │   ├── runtime.py        # 执行运行时
│   │   ├── checkpoint.py     # 持久化与恢复
│   │   └── adapters.py       # 服务适配与消息窗口
│   ├── tools/                # 工具系统（11 个模块）
│   │   ├── registry.py       # 统一工具注册表
│   │   ├── engine.py         # 执行引擎（超时/重试）
│   │   ├── order_tools.py    # 订单查询工具
│   │   ├── ticket_tools.py   # 工单创建工具
│   │   ├── mcp_client.py     # MCP 客户端与发现
│   │   ├── audit.py          # 工具调用审计
│   │   └── formatting.py     # 结果格式化
│   ├── kb/                   # 知识库管理（9 个模块）
│   │   ├── documents.py      # Markdown 解析
│   │   ├── chunking.py       # 文档切块
│   │   ├── dualwrite.py      # MySQL + Milvus 双写
│   │   ├── milvus_client.py  # Milvus 操作
│   │   ├── mining.py         # 从日志提取知识
│   │   ├── review_publish.py # 审核与发布流程
│   │   └── ...
│   ├── db/                   # 数据库层（4 个模块）
│   │   ├── models.py         # SQLAlchemy 模型（12 张表）
│   │   ├── repository.py     # 数据访问层
│   │   └── database.py       # 异步会话工厂
│   ├── schemas/              # Pydantic 数据模型
│   ├── static/               # Web UI（HTML/CSS/JS）
│   ├── config.py             # 配置管理
│   └── main.py               # 应用入口
├── data/
│   ├── kb/                   # 示例知识库（6 个 markdown 文件）
│   ├── eval/                 # 评测数据集
│   └── finetune/             # 本地微调数据与报告
├── migrations/               # Alembic 迁移
├── scripts/                  # 维护脚本（28 个脚本）
│   ├── tasks.py              # 统一 CLI 入口
│   ├── build_kb.py           # 构建知识库
│   ├── vectorize_kb.py       # 向量化任务
│   ├── eval_retrieval.py     # RAG 评测
│   ├── cost_by_intent.py     # 成本报告
│   └── finetune/             # 分类器训练流程
├── .env.example              # 环境变量模板
├── docker-compose.yml        # MySQL + Milvus + etcd + MinIO
├── docker-compose.langfuse.yml # 可选 Langfuse 栈
└── pyproject.toml            # 依赖管理（uv）
```

---

## 🚀 快速开始

### 前置要求

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** 包管理器
- **Docker & Docker Compose**
- **OpenAI 兼容的 LLM 和 Embedding API**

### 1. 安装依赖

```bash
# 复制环境变量模板
cp .env.example .env

# 安装 Python 依赖
uv sync --group dev
```

### 2. 配置环境

编辑 `.env` 文件，至少配置：

```env
# LLM 配置
CHAT_MODEL=gpt-4o-mini
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=sk-...
CHAT_THINKING=disabled

# Embedding 配置
EMBED_MODEL=text-embedding-3-small
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=sk-...

# 可选：重排序
RERANK_BASE_URL=https://api.siliconflow.cn/v1
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_API_KEY=...

# 数据库（必填；此 URL 对应项目自带的 docker-compose 配置）
MYSQL_DATABASE_URL=mysql+asyncmy://root:root@127.0.0.1:3308/minihelp_complete
MILVUS_URI=http://127.0.0.1:19531

# 可选：主题分类服务基础地址
CLASSIFIER_URL=http://127.0.0.1:8110

# RAG 参数
RECALL_TOP_K=50
RERANK_TOP_K=10
RERANK_MIN_SCORE=0.3
EVIDENCE_MIN_CONFIDENCE=0.5
SUBQUERY_SPLIT=true
```

> ⚠️ **安全提示**：不要提交包含真实密钥的 `.env` 文件

`MYSQL_DATABASE_URL` 是必填项，没有默认值。`.env.example` 中的 `MILVUS_URI` 与 Settings 默认值一致（`http://127.0.0.1:19530`）；项目自带的 Docker Compose 将 Milvus 映射到宿主机端口 `19531`，使用该配置时请按上面的示例覆盖地址。启动时会仅按键名告警 `.env` 中的未知配置键；检查点配置名为 `GRAPH_CHECKPOINT_PATH`。

### 3. 启动数据服务

```bash
# 启动 MySQL、Milvus、etcd、MinIO
docker compose up -d

# 验证服务状态
docker compose ps

# 执行迁移
uv run alembic upgrade head
```

**服务端口：**
- MySQL: `127.0.0.1:3308`（数据库：`minihelp_complete`）
- Milvus: `127.0.0.1:19531`
- MinIO（Milvus 存储）: `127.0.0.1:9000`

### 4. 初始化知识库

```bash
# 预览切块（不写库）
uv run python -m scripts.tasks kb-preview

# 写入 MySQL
uv run python -m scripts.tasks kb-build

# 向量化到 Milvus
uv run python -m scripts.tasks kb-vectorize
```

示例知识库包含 6 个 markdown 文件：
- `product-specs.md` - 产品规格
- `product-faq.md` - 产品常见问题
- `returns-policy.md` - 退货政策
- `billing-shipping.md` - 账单与物流
- `member-benefits.md` - 会员权益
- `after-sales-manual.md` - 售后手册

### 5. 启动应用

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

会话锁（`app/core/conversation_lock.py`）、限流等协调状态保存在进程内存中。当前应用仅支持单进程部署，即 Uvicorn 使用单个 worker。多实例部署需要外部锁和共享存储，不在本项目范围内。

访问：**http://127.0.0.1:8000**

---

## 📱 功能页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 🏠 **聊天** | `/` | 客服对话界面 |
| 🎛️ **管理** | `/admin` | 系统概览仪表板 |
| 📚 **知识库** | `/kb` | 知识管理与检索测试 |
| ✅ **审核** | `/review` | 待审核知识队列 |
| 📊 **观测** | `/observability` | 执行追踪与模型用量 |
| 🏷️ **主题** | `/topics` | 按主题统计问题分布 |
| 🔬 **RAG 评测** | `/rag-eval` | 检索质量评估 |
| 🎯 **验收** | `/acceptance` | 分类器性能指标 |
| 📖 **API 文档** | `/docs` | FastAPI 自动生成文档 |

---

## 🧪 主题分类器（可选）

17 类多标签问题分类器，支持微调。

### 训练流程

```bash
# 安装机器学习依赖
uv sync --group dev --group ml

# 1. 验证黄金标注集
uv run --group ml python -m scripts.tasks finetune-golden

# 2. 使用 LLM 生成训练语料
uv run --group ml python -m scripts.tasks finetune-corpus

# 3. 构建训练/验证/测试集
uv run --group ml python -m scripts.tasks finetune-dataset

# 4. 微调分类器
uv run --group ml python -m scripts.tasks finetune-train

# 5. 在测试集上评估
uv run --group ml python -m scripts.tasks finetune-eval

# 6. 导出为 ONNX
uv run --group ml python -m scripts.tasks finetune-export

# 7. 启动推理服务（端口 8110）
uv run --group ml python -m scripts.tasks classifier-up
```

> 📝 **注意**：需要在 `data/finetune/pretrained/` 目录下放置中文 RoBERTa-wwm-ext 基础权重

**验收标准：**
- **严格档**：F1 ≥ 0.9（每标签微平均）
- **中档**：F1 ≥ 0.8

验收页面在未达标时会显示错例样本和改进建议。

---

## 🔧 开发

### 检查 Python 语法

```bash
python -m compileall -q app scripts migrations
```

### 数据库迁移

```bash
# 创建迁移
uv run alembic revision --autogenerate -m "描述"

# 应用迁移
uv run alembic upgrade head

# 回退
uv run alembic downgrade -1
```

### 知识库操作

```bash
# 统一任务入口
uv run python -m scripts.tasks

# 可用任务：
# kb-preview       预览文档切块
# kb-build         写入 MySQL
# kb-vectorize     向量化并写入 Milvus
```

### 成本报告

```bash
# 按意图生成成本报告
uv run python -m scripts.tasks cost-by-intent
```

### 启用 Langfuse（可选）

```bash
# 启动本地 Langfuse 栈
docker compose -f docker-compose.langfuse.yml up -d

# 在 .env 中配置
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=http://127.0.0.1:3000
```

### 启用 MCP 工具（可选）

```bash
# 在 .env 中配置 MCP 服务器 URL
MCP_LOGISTICS_URL=http://127.0.0.1:8100
MCP_AFTERSALES_URL=http://127.0.0.1:8101
```

MCP 工具在启动时发现。检查日志中的 `"MCP 工具发现异常"` 警告。

---

## 📊 数据库表结构

12 张表，覆盖会话、知识、审计和可观测性：

| 表名 | 用途 |
|------|------|
| `conversations` | 会话记录（带摘要） |
| `messages` | 消息历史（user/assistant/tool） |
| `tickets` | 客户工单 |
| `knowledge_chunks` | 知识块（pending/done） |
| `qa_extraction_staging` | 挖掘的候选知识 |
| `reviews` | 知识审核队列 |
| `low_confidence_questions` | 需审核的问题 |
| `turns` | 每轮回答快照（意图、证据、置信度） |
| `tool_audit_logs` | 工具调用审计轨迹 |
| `trace_spans` | 执行追踪跨度 |
| `topic_classifications` | 17 类主题标签 |
| `eval_runs` | 固定集评测运行结果 |

---

## 🔍 核心流程

### 对话流程

```
用户输入
  ↓
意图识别（9 类）
  ↓
  ├─→ 商品咨询 → 知识检索 → 证据评估 → 回答
  ├─→ 订单查询 → 订单工具 → 返回结果
  ├─→ 退款退货 → 工单工具 → 确认 → 创建工单
  ├─→ 物流/售后 → MCP 工具 → 外部服务调用
  └─→ 人工客服 → 转人工
```

**意图类别：**
- 物流
- 订单
- 商品咨询
- 退款退货
- 售后
- 投诉
- 人工
- 闲聊
- 其他

### 知识流程

```
Markdown 文档
  ↓
解析与切块（按 content_type: faq/policy/manual）
  ↓
写入 MySQL（status=pending）
  ↓
调用 Embedding API
  ↓
写入 Milvus + 更新 MySQL（status=done）
  ↓
用户查询 → 向量检索 → 可选重排序 → 证据
```

**内容类型：**
- `faq`：问答对
- `policy`：政策条款（带章节路径）
- `manual`：操作说明

### 质量闭环

```
收集低置信度问题
  ↓
人工审核
  ↓
知识挖掘 → LLM 提取 Q&A
  ↓
暂存审核 → 批准/拒绝
  ↓
发布到知识库 → 自动向量化
  ↓
相似问题置信度提升
```

---

## 📈 关键设计决策

以下是主要架构选择：

1. **LangGraph 编排**
   - 带检查点的状态化对话流程
   - 中断后可恢复执行（工单确认）
   - 可视化图结构便于调试

2. **统一工具系统**
   - 基于注册表的工具发现（本地 + MCP）
   - 标准化执行引擎（超时/重试）
   - 完整审计轨迹与重放能力
   - 工具身份上下文实现权限隔离

3. **带置信度门控的 RAG**
   - 回答前评估证据充分性
   - 可配置置信度阈值
   - 证据不足时拒绝回答

4. **滚动对话摘要**
   - 可配置间隔的自动摘要
   - 摘要感知的意图识别
   - 减少上下文窗口使用

5. **按意图成本归因**
   - 按对话意图追踪 token 用量
   - 支持业务级成本优化
   - 识别高成本交互模式

6. **MCP 协议集成**
   - 外部工具的标准协议
   - 带流式支持的 HTTP 传输
   - 运行时发现与错误处理

---

## 🤝 贡献

本项目主要用于学习和演示，暂未开放外部贡献。

如有疑问或建议，请提交 Issue。

---
## 🙏 致谢

- [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Milvus](https://milvus.io/)
- [OpenAI](https://openai.com/)
- [Langfuse](https://langfuse.com/)

---

## 📮 联系方式

如有问题，请通过 GitHub Issues 反馈。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。运行数据、模型权重、本地测试文件和 `.env` 不包含在公开仓库中。
