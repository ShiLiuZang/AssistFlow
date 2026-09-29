# 智能客服系统

> 面向电商场景的智能客服平台 · 集成对话管理、知识问答、业务办理与质量运营

这是一个完整的电商智能客服系统，采用 **FastAPI + LangGraph + MySQL + Milvus** 技术栈构建。系统支持自然语言对话、知识库检索、订单查询、工单处理，并提供完整的知识运营和质量监控能力。

## ✨ 核心特性

### 🤖 智能对话
- 流式响应，实时交互体验
- 多轮对话上下文管理
- 意图识别与智能路由
- 对话摘要与历史压缩

### 📚 知识问答
- 向量检索 + 可选重排序
- 证据充分性自动判断
- 问题拆分与多路检索
- 知识库审核发布流程

### 🛠️ 业务工具
- 订单查询（权限隔离）
- 工单创建与确认流程
- MCP 协议集成外部服务（物流、售后）
- 工具调用审计与重放

### 📊 质量闭环
- 低置信度问题收集
- 用户反馈管理
- 执行追踪与可观测性
- 模型用量统计（按意图口径）
- 17 类问题主题分类器

### 🔧 开发友好
- 完整的中文代码注释
- 单元测试与集成测试
- 本地开发环境一键启动
- 可选 Langfuse 观测集成

---

## 🏗️ 系统架构

```
┌─────────────┐
│  用户/管理员 │
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────┐
│            FastAPI Web 层                    │
│  路由：聊天、知识、审核、观测、主题分析      │
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
| **LLM 调用** | OpenAI 兼容 Chat API |
| **工具集成** | MCP (Model Context Protocol) |
| **可观测性** | 本地追踪 + 可选 Langfuse |
| **主题分类** | PyTorch + Transformers + ONNX Runtime |
| **前端** | 原生 HTML/CSS/JavaScript |

---

## 📁 项目结构

```
智能客服/
├── app/                      # 应用主目录
│   ├── api/                  # FastAPI 路由
│   │   ├── chat.py           # 基础聊天接口
│   │   ├── graph_chat.py     # LangGraph 聊天接口
│   │   ├── conversations.py  # 会话管理
│   │   ├── knowledge.py      # 知识检索与评测
│   │   ├── observability.py  # 执行追踪与观测
│   │   ├── feedback.py       # 用户反馈
│   │   ├── review.py         # 知识审核
│   │   ├── topics.py         # 主题分类
│   │   └── acceptance.py     # 分类器验收
│   ├── core/                 # 核心业务逻辑
│   │   ├── llm.py            # LLM 客户端
│   │   ├── embeddings.py     # 向量化
│   │   ├── retrieval.py      # 知识检索
│   │   ├── rerank.py         # 重排序
│   │   ├── intent.py         # 意图识别
│   │   ├── evidence.py       # 证据评估
│   │   ├── confidence.py     # 置信度判断
│   │   ├── coref.py          # 指代消解
│   │   ├── summarizer.py     # 对话摘要
│   │   └── observability.py  # 观测追踪
│   ├── graph/                # LangGraph 对话图
│   │   ├── state.py          # 状态定义
│   │   ├── nodes.py          # 节点实现
│   │   ├── routing.py        # 路由决策
│   │   ├── build.py          # 图构建
│   │   ├── runtime.py        # 运行时
│   │   └── checkpoint.py     # 检查点管理
│   ├── tools/                # 工具系统
│   │   ├── registry.py       # 工具注册表
│   │   ├── engine.py         # 工具执行引擎
│   │   ├── order_tools.py    # 订单查询工具
│   │   ├── ticket_tools.py   # 工单创建工具
│   │   ├── knowledge_tools.py# 知识检索工具
│   │   ├── mcp_client.py     # MCP 客户端
│   │   └── audit.py          # 工具审计
│   ├── kb/                   # 知识库管理
│   │   ├── documents.py      # 文档解析
│   │   ├── chunking.py       # 文档切块
│   │   ├── dualwrite.py      # 双写（MySQL + Milvus）
│   │   ├── milvus_client.py  # Milvus 客户端
│   │   ├── mining.py         # 知识挖掘
│   │   └── review_publish.py # 审核发布
│   ├── db/                   # 数据库层
│   │   ├── models.py         # SQLAlchemy 模型
│   │   ├── repository.py     # 数据访问层
│   │   └── database.py       # 数据库连接
│   ├── static/               # 静态资源（HTML/CSS/JS）
│   ├── schemas/              # Pydantic 数据模型
│   ├── config.py             # 配置管理
│   └── main.py               # 应用入口
├── data/
│   ├── kb/                   # 示例知识库材料
│   └── eval/                 # 评测数据集
├── migrations/               # Alembic 数据库迁移
├── scripts/                  # 脚本工具
│   ├── tasks.py              # 统一任务入口
│   ├── build_kb.py           # 构建知识库
│   ├── vectorize_kb.py       # 向量化
│   ├── eval_ch04.py          # RAG 评测
│   └── ch10/                 # 主题分类器相关
├── tests/                    # 测试用例
├── .env.example              # 环境变量模板
├── docker-compose.yml        # Docker 服务编排
├── pyproject.toml            # 项目依赖
└── README.md
```

---

## 🚀 快速开始

### 前置要求

- **Python 3.12+**
- **uv** ([安装文档](https://docs.astral.sh/uv/))
- **Docker & Docker Compose**
- **OpenAI 兼容的 LLM 和 Embedding 接口**

### 一、安装依赖

```bash
# 复制环境变量模板
cp .env.example .env

# 安装 Python 依赖
uv sync --group dev
```

### 二、配置环境变量

编辑 `.env` 文件，至少配置以下项：

```env
# LLM 模型配置
CHAT_MODEL=gpt-4o-mini
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=sk-...

# Embedding 模型配置
EMBED_MODEL=text-embedding-3-small
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=sk-...

# 数据库配置（使用 docker-compose 时保持默认）
HANDWRITTEN_DATABASE_URL=mysql+asyncmy://root:root@127.0.0.1:3308/minihelp_complete

# Milvus 配置
MILVUS_URI=http://127.0.0.1:19530
```

> ⚠️ **安全提示**：不要将包含真实密钥的 `.env` 文件提交到版本控制系统

### 三、启动数据服务

```bash
# 启动 MySQL 和 Milvus
docker compose up -d mysql etcd minio milvus

# 检查服务状态
docker compose ps

# 执行数据库迁移
uv run alembic upgrade head
```

### 四、初始化知识库

```bash
# 预览切块结果（不写库）
uv run python -m scripts.tasks kb-preview

# 将示例材料写入 MySQL
uv run python -m scripts.tasks kb-build

# 向量化并写入 Milvus
uv run python -m scripts.tasks kb-vectorize
```

### 五、启动应用

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

应用启动后访问：**http://127.0.0.1:8000**

---

## 📱 功能页面

| 页面 | 地址 | 说明 |
|------|------|------|
| 🏠 **聊天首页** | `/` | 智能客服对话界面 |
| 🎛️ **管理后台** | `/admin` | 系统管理总览 |
| 📚 **知识库** | `/kb` | 知识块预览、录入、检索测试 |
| ✅ **知识审核** | `/review` | 待审核知识列表 |
| 📊 **执行观测** | `/observability` | 追踪记录与模型用量 |
| 🏷️ **主题分布** | `/topics` | 问题分类统计与分析 |
| 🔬 **RAG 评测** | `/rag-eval` | 检索质量评估 |
| 🎯 **分类验收** | `/acceptance` | 分类器性能指标 |
| 📖 **API 文档** | `/docs` | FastAPI 自动生成文档 |

---

## 🧪 主题分类器（可选）

主题分类器用于对用户问题进行 17 类多标签分类，支持问题分布分析和错例诊断。

### 训练流程

```bash
# 安装机器学习依赖
uv sync --group dev --group ml

# 1. 准备黄金标注集
uv run --group ml python -m scripts.tasks ch10-golden

# 2. 生成训练语料
uv run --group ml python -m scripts.tasks ch10-corpus

# 3. 构建数据集
uv run --group ml python -m scripts.tasks ch10-dataset

# 4. 训练模型
uv run --group ml python -m scripts.tasks ch10-train

# 5. 评估模型
uv run --group ml python -m scripts.tasks ch10-eval

# 6. 导出 ONNX
uv run --group ml python -m scripts.tasks ch10-export

# 7. 启动分类服务（监听 8110 端口）
uv run --group ml python -m scripts.tasks classifier-up
```

> 📝 **注意**：训练需要在 `data/ch10/pretrained/` 目录下放置兼容的中文 RoBERTa-wwm-ext 基础权重文件。

---

## 🔧 开发指南

### 运行测试

```bash
# 运行所有测试
uv run pytest tests -v

# 运行特定测试
uv run pytest tests/test_ch06_integration.py -v

# 跳过前端测试
uv run pytest tests -q --ignore=tests/test_ch05_frontend.py --ignore=tests/test_ch06_frontend.py
```

### 数据库迁移

```bash
# 创建新迁移
uv run alembic revision --autogenerate -m "描述变更内容"

# 应用迁移
uv run alembic upgrade head

# 回退迁移
uv run alembic downgrade -1
```

### 知识库管理

```bash
# 统一任务入口
uv run python -m scripts.tasks

# 可用任务：
# kb-preview       预览切块
# kb-build         构建知识库
# kb-vectorize     向量化
# kb-review        审核界面
```

### 可选集成

**启用 Langfuse 观测**：
```bash
# 启动本地 Langfuse（可选）
docker compose -f docker-compose.langfuse.yml up -d

# 在 .env 中配置
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=http://127.0.0.1:3000
```

**启用 MCP 工具**：
```bash
# 在 .env 中配置 MCP 服务地址
MCP_LOGISTICS_URL=http://127.0.0.1:8100
MCP_AFTERSALES_URL=http://127.0.0.1:8101
```

---

## 📊 数据库表结构

| 表名 | 用途 |
|------|------|
| `conversations` | 会话记录 |
| `messages` | 消息历史 |
| `tickets` | 工单记录 |
| `knowledge_chunks` | 知识块（待向量化/已完成） |
| `qa_extraction_staging` | 挖掘的候选知识 |
| `reviews` | 知识审核队列 |
| `low_confidence_questions` | 低置信度问题 |
| `user_feedback` | 用户反馈 |
| `tool_audit_logs` | 工具调用审计 |
| `trace_spans` | 执行追踪记录 |
| `topic_classifications` | 主题分类结果 |

---

## 🔍 核心流程说明

### 对话流程

```
用户输入
  ↓
意图识别 ──→ 人工/闲聊 ──→ 直接回复
  ↓
  ├─→ 商品咨询 ──→ 知识检索 ──→ 证据评估 ──→ 生成回答
  ├─→ 订单查询 ──→ 调用订单工具 ──→ 返回结果
  ├─→ 工单创建 ──→ 确认流程 ──→ 创建工单
  └─→ 物流/售后 ──→ MCP 工具 ──→ 外部服务
```

### 知识库流程

```
Markdown 文档
  ↓
文档解析与切块
  ↓
写入 MySQL (pending)
  ↓
调用 Embedding API
  ↓
写入 Milvus + 更新状态 (done)
  ↓
用户查询 → 向量检索 → 可选重排序 → 返回证据
```

### 质量闭环

```
低置信度问题收集
  ↓
人工审核
  ↓
知识挖掘 → 生成候选知识
  ↓
审核发布 → 加入知识库
  ↓
再次遇到类似问题 → 高置信度回答
```

---

## 🤝 贡献指南

本项目主要用于学习和演示，暂未开放外部贡献。如有疑问或建议，欢迎提交 Issue。

---

## 📄 许可证

本项目暂未包含许可证文件。如需对外分发或商业使用，请先明确授权条款。

---

## 🙏 致谢

- [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Milvus](https://milvus.io/)
- [OpenAI](https://openai.com/)

---

## 📮 联系方式

如有问题，请通过 GitHub Issues 反馈。
