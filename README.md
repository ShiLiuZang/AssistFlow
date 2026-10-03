# AI Customer Service Platform

> Enterprise-grade AI customer service system for e-commerce · Dialogue Management, Knowledge Q&A, Business Processing & Quality Operations

[简体中文](./README.zh-CN.md) | English

An enterprise-grade e-commerce AI customer service system built with **FastAPI + LangGraph + MySQL + Milvus**. Features natural language conversations, knowledge base retrieval, order queries, ticket processing, and comprehensive knowledge operations with quality monitoring.

## ✨ Key Features

### 🤖 Intelligent Dialogue
- **Streaming responses** with real-time SSE protocol
- **Multi-turn context management** with conversation summarization
- **Intent recognition** and intelligent routing (9 intent categories)
- **Coreference resolution** for entity tracking across turns

### 📚 Knowledge Q&A (RAG)
- **Vector retrieval** with Milvus + optional reranking
- **Evidence sufficiency assessment** with confidence scoring
- **Query decomposition** and multi-path retrieval
- **Knowledge review workflow** with staging and approval

### 🛠️ Business Tools
- **Order queries** with user permission isolation
- **Ticket creation** with confirmation workflow
- **MCP integration** for external services (logistics, after-sales)
- **Tool audit** with complete invocation history and replay

### 📊 Quality & Observability
- **Low-confidence tracking** with feedback collection
- **Execution tracing** with Langfuse integration (optional)
- **Model usage reporting** by intent category
- **17-class topic classifier** with fine-tuning support

### 🔧 Developer Experience
- **Comprehensive Chinese comments** across all modules
- **Local verification scripts** for selected workflows
- **Database migrations** with Alembic
- **One-command setup** with Docker Compose

---

## 🏗️ System Architecture

```
┌─────────────┐
│  User/Admin │
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────┐
│            FastAPI Web Layer                 │
│  Routes: Chat, Knowledge, Review, Observe    │
└──────┬──────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────┐
│      LangGraph Conversation Orchestration    │
│  Nodes: Intent→Retrieval→Tools→Answer→Summary│
└─┬──────┬──────┬──────┬─────────────────────┘
  │      │      │      │
  │      │      │      └─→ [Order/Ticket/MCP Tools]
  │      │      └────────→ [Milvus Vector Search]
  │      └───────────────→ [LLM Services]
  └──────────────────────→ [MySQL Business Data]
```

### Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Web Framework** | FastAPI + Uvicorn |
| **Conversation Orchestration** | LangGraph + LangChain |
| **Data Storage** | MySQL (SQLAlchemy + Alembic) + SQLite (conversation checkpoints) |
| **Vector Search** | Milvus + OpenAI-compatible Embedding API |
| **LLM** | OpenAI-compatible Chat API (supports thinking mode) |
| **Tool Integration** | MCP (Model Context Protocol) |
| **Observability** | Local tracing + Optional Langfuse |
| **Topic Classification** | PyTorch + Transformers + ONNX Runtime |
| **Frontend** | Vue 3 + TypeScript + Vite (`frontend/web`) |

---

## 📁 Project Structure

```
智能客服/
├── app/
│   ├── api/                  # FastAPI routes (15 modules)
│   │   ├── graph_chat.py     # LangGraph streaming chat
│   │   ├── chat.py           # Basic chat with tool calls
│   │   ├── conversations.py  # Conversation history
│   │   ├── knowledge.py      # Knowledge retrieval & RAG eval
│   │   ├── observability.py  # Execution traces & usage
│   │   ├── feedback.py       # User feedback
│   │   ├── review.py         # Knowledge review queue
│   │   ├── topics.py         # Topic classification
│   │   ├── acceptance.py     # Classifier validation
│   │   └── ...
│   ├── core/                 # Business logic (28 modules)
│   │   ├── llm.py            # LLM client factory
│   │   ├── embeddings.py     # Text vectorization
│   │   ├── retrieval.py      # Unified retrieval interface
│   │   ├── rerank.py         # Optional reranking
│   │   ├── intent.py         # Intent classification
│   │   ├── evidence.py       # Evidence assessment
│   │   ├── confidence.py     # Confidence scoring
│   │   ├── coref.py          # Coreference resolution
│   │   ├── summarizer.py     # Rolling conversation summary
│   │   ├── observability.py  # Tracing & token usage
│   │   └── ...
│   ├── graph/                # LangGraph implementation (8 modules)
│   │   ├── state.py          # Conversation state schema
│   │   ├── nodes.py          # Node implementations
│   │   ├── routing.py        # Conditional routing
│   │   ├── build.py          # Graph assembly
│   │   ├── runtime.py        # Execution runtime
│   │   ├── checkpoint.py     # Persistence & recovery
│   │   └── adapters.py       # Service wiring & message window
│   ├── tools/                # Tool system (11 modules)
│   │   ├── registry.py       # Unified tool registry
│   │   ├── engine.py         # Execution with timeout/retry
│   │   ├── order_tools.py    # Order query tool
│   │   ├── ticket_tools.py   # Ticket creation tool
│   │   ├── knowledge_tools.py# Knowledge retrieval tool
│   │   ├── mcp_client.py     # MCP client & discovery
│   │   ├── audit.py          # Tool invocation audit
│   │   └── formatting.py     # Result formatting
│   ├── kb/                   # Knowledge base management (9 modules)
│   │   ├── documents.py      # Markdown parsing
│   │   ├── chunking.py       # Document chunking
│   │   ├── dualwrite.py      # MySQL + Milvus dual-write
│   │   ├── milvus_client.py  # Milvus operations
│   │   ├── mining.py         # Knowledge extraction from logs
│   │   ├── review_publish.py # Review & publish workflow
│   │   └── ...
│   ├── db/                   # Database layer (4 modules)
│   │   ├── models.py         # SQLAlchemy models (13 tables)
│   │   ├── repository.py     # Data access layer
│   │   └── database.py       # Async session factory
│   ├── schemas/              # Pydantic models
│   ├── config.py             # Configuration management
│   └── main.py               # Application entry
├── data/
│   ├── kb/                   # Sample knowledge (6 markdown files)
│   ├── eval/                 # Evaluation datasets
│   └── finetune/             # Local fine-tuning data and reports
├── migrations/               # Alembic migrations
├── scripts/                  # Maintenance scripts (28 scripts)
│   ├── tasks.py              # Unified CLI entry
│   ├── build_kb.py           # Build knowledge base
│   ├── vectorize_kb.py       # Vectorization job
│   ├── eval_04.py            # RAG evaluation
│   ├── cost_by_intent.py     # Cost reporting
│   └── finetune/             # Classifier training pipeline
├── .env.example              # Environment template
├── docker-compose.yml        # MySQL + Milvus + etcd + MinIO
├── docker-compose.langfuse.yml # Optional Langfuse stack
└── pyproject.toml            # Dependencies (uv)
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** package manager
- **Docker & Docker Compose**
- **OpenAI-compatible LLM and Embedding API**

### 1. Install Dependencies

```bash
# Copy environment template
cp .env.example .env

# Install Python dependencies
uv sync --group dev
```

### 2. Configure Environment

Edit `.env` with at least:

```env
# LLM Configuration
CHAT_MODEL=gpt-4o-mini
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=sk-...
CHAT_THINKING=disabled

# Embedding Configuration
EMBED_MODEL=text-embedding-3-small
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=sk-...

# Optional: Reranking
RERANK_BASE_URL=https://api.siliconflow.cn/v1
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_API_KEY=...

# Database (keep default when using docker-compose)
HANDWRITTEN_DATABASE_URL=mysql+asyncmy://root:root@127.0.0.1:3308/minihelp_complete
MILVUS_URI=http://127.0.0.1:19531

# RAG Parameters
RECALL_TOP_K=50
RERANK_TOP_K=10
RERANK_MIN_SCORE=0.3
EVIDENCE_MIN_CONFIDENCE=0.5
SUBQUERY_SPLIT=true
```

> ⚠️ **Security**: Never commit `.env` with real credentials

### 3. Start Data Services

```bash
# Start MySQL, Milvus, etcd, MinIO
docker compose up -d

# Verify services
docker compose ps

# Run migrations
uv run alembic upgrade head
```

**Service Ports:**
- MySQL: `127.0.0.1:3308` (database: `minihelp_complete`)
- Milvus: `127.0.0.1:19531`
- MinIO (Milvus storage): `127.0.0.1:9000`

**Create a back-office account** (roles: `admin`, `reviewer`, `agent`):

```bash
uv run python -m scripts.tasks staff-create --username admin --role admin
```

Back-office pages require staff login. Customer identity comes from tokens signed by the storefront backend (sharing `CUSTOMER_TOKEN_SECRET`); for local development set `AUTH_DEV_MODE=true` in `.env` and enter any customer ID on the chat page.

**Human handoff:** create `agent` accounts for customer-service staff. When a customer asks for a human (or complains, or clicks 转人工), the conversation enters the queue on `#/workbench`; once an agent accepts it the AI is paused until the agent ends the session. Real-time push uses in-process SSE, so run a single API instance for now. See [docs/phase2-human-handoff.md](docs/phase2-human-handoff.md).

**Pinduoduo channel:** set `PDD_ENABLED=true` and `PDD_BRIDGE_SECRET` (32+ chars). Buyer messages arrive from a channel bridge at `POST /api/channels/pinduoduo/events` (HMAC-signed); replies, staff messages and handoff notices go back through `PDD_BRIDGE_SEND_URL` (left empty, replies are only recorded). Bursts are merged into one turn, a holding reply goes out when an answer is slow, and ticket confirmation / order selection work by text. Buyers can only query orders they sent as order cards; set `PDD_CLIENT_ID` / `PDD_CLIENT_SECRET` / `PDD_ACCESS_TOKEN` to look up live order status. See [docs/phase3-pinduoduo-channel.md](docs/phase3-pinduoduo-channel.md).

### 4. Initialize Knowledge Base

```bash
# Preview chunking (no write)
uv run python -m scripts.tasks kb-preview

# Write to MySQL
uv run python -m scripts.tasks kb-build

# Vectorize to Milvus
uv run python -m scripts.tasks kb-vectorize
```

Sample knowledge includes 6 markdown files:
- `product-specs.md` - Product specifications
- `product-faq.md` - Product FAQs
- `returns-policy.md` - Return policy
- `billing-shipping.md` - Billing & shipping
- `member-benefits.md` - Membership benefits
- `after-sales-manual.md` - After-sales manual

### 5. Build the Frontend and Start the Application

```bash
cd frontend/web && npm install && npm run build && cd ../..   # requires Node.js 22.6+
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For frontend development use `npm run dev` instead (http://localhost:5173, proxies `/api` to port 8000).

Visit: **http://127.0.0.1:8000**

---

## 📱 Feature Pages

The frontend is a Vue single-page app with hash routing.

| Page | Route | Description |
|------|-------|-------------|
| 🏠 **Customer Chat** | `/#/client` | Customer service chat interface |
| 🎛️ **Overview** | `/#/overview` | System overview dashboard |
| 📚 **Knowledge** | `/#/knowledge` | Knowledge management, candidates & retrieval test |
| ✅ **Review** | `/#/review` | Pending knowledge review queue |
| 🔬 **RAG Quality** | `/#/quality` | Retrieval and generation evaluation |
| 📊 **Observability** | `/#/observability` | Execution traces & model usage |
| 🏷️ **Topics** | `/#/topics` | Question distribution by topic |
| 🎯 **Classifier** | `/#/models` | Classifier acceptance & evaluation |
| ⚙️ **Jobs** | `/#/jobs` | Start and stop background jobs |
| 📖 **API Docs** | `/docs` | FastAPI auto-generated documentation |

------|-------|-------------|
| 🏠 **Chat** | `/` | Customer service chat interface |
| 🎛️ **Admin** | `/admin` | System overview dashboard |
| 📚 **Knowledge** | `/kb` | Knowledge management & retrieval test |
| ✅ **Review** | `/review` | Pending knowledge review queue |
| 📊 **Observability** | `/observability` | Execution traces & model usage |
| 🏷️ **Topics** | `/topics` | Question distribution by topic |
| 🔬 **RAG Eval** | `/rag-eval` | Retrieval quality assessment |
| 🎯 **Acceptance** | `/acceptance` | Classifier performance metrics |
| 📖 **API Docs** | `/docs` | FastAPI auto-generated documentation |

---

## 🧪 Topic Classifier (Optional)

17-class multi-label question classifier with fine-tuning support.

### Training Pipeline

```bash
# Install ML dependencies
uv sync --group dev --group ml

# 1. Validate golden labeled set
uv run --group ml python -m scripts.tasks finetune-golden

# 2. Generate training corpus with LLM
uv run --group ml python -m scripts.tasks finetune-corpus

# 3. Build train/val/test datasets
uv run --group ml python -m scripts.tasks finetune-dataset

# 4. Fine-tune classifier
uv run --group ml python -m scripts.tasks finetune-train

# 5. Evaluate on test set
uv run --group ml python -m scripts.tasks finetune-eval

# 6. Export to ONNX
uv run --group ml python -m scripts.tasks finetune-export

# 7. Start inference service (port 8110)
uv run --group ml python -m scripts.tasks classifier-up
```

> 📝 **Note**: Requires Chinese RoBERTa-wwm-ext base weights in `data/finetune/pretrained/`

**Validation Criteria:**
- **Strict**: F1 ≥ 0.9 (per-label micro-average)
- **Medium**: F1 ≥ 0.8

Acceptance page shows error samples and improvement suggestions when criteria are not met.

---

## 🔧 Development

### Check Python Syntax

```bash
python -m compileall -q app scripts migrations
```

### Run Unit Tests

Unit tests live in `tests/`. LLM, Milvus and MySQL are mocked, so no `.env` or external service is needed.

```bash
uv sync --group dev
uv run pytest
```

### Database Migrations

```bash
# Create migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1
```

### Knowledge Base Operations

```bash
# Unified task entry
uv run python -m scripts.tasks

# Available tasks:
# kb-preview       Preview document chunking
# kb-build         Write chunks to MySQL
# kb-vectorize     Vectorize and write to Milvus
```

### Cost Reporting

```bash
# Generate cost report by intent
uv run python -m scripts.tasks cost-by-intent
```

### Enable Langfuse (Optional)

```bash
# Start local Langfuse stack
docker compose -f docker-compose.langfuse.yml up -d

# Configure in .env
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=http://127.0.0.1:3000
```

### Enable MCP Tools (Optional)

```bash
# Configure MCP server URLs in .env
MCP_LOGISTICS_URL=http://127.0.0.1:8100
MCP_AFTERSALES_URL=http://127.0.0.1:8101
```

MCP tools are discovered at startup. Check logs for `"MCP 工具发现异常"` warnings.

---

## 📊 Database Schema

13 tables covering conversation, knowledge, audit, and observability:

| Table | Purpose |
|-------|---------|
| `conversations` | Conversation records with summary |
| `messages` | Message history (user/assistant/tool) |
| `tickets` | Customer tickets |
| `knowledge_chunks` | Knowledge blocks (pending/done) |
| `qa_extraction_staging` | Mined candidate knowledge |
| `reviews` | Knowledge review queue |
| `low_confidence_questions` | Questions needing review |
| `user_feedback` | User satisfaction feedback |
| `tool_audit_logs` | Tool invocation audit trail |
| `trace_spans` | Execution trace spans |
| `topic_classifications` | 17-class topic labels |
| `model_usage_logs` | Token usage by intent |
| `cost_attribution` | Cost allocation |
| `handoffs`, `ticket_events` | Human handoff and ticket workflow |
| `channel_sessions`, `channel_messages`, `channel_orders` | Pinduoduo buyers, inbound/outbound log, order ownership |

---

## 🔍 Core Workflows

### Conversation Flow

```
User Input
  ↓
Intent Recognition (9 classes)
  ↓
  ├─→ 商品咨询 → Knowledge Retrieval → Evidence Assessment → Answer
  ├─→ 订单查询 → Order Tool → Return Results
  ├─→ 退款退货 → Ticket Tool → Confirmation → Create Ticket
  ├─→ 物流/售后 → MCP Tools → External Service Call
  └─→ 人工客服 → Human Handoff
```

**Intent Categories:**
- 物流 (Logistics)
- 订单 (Order)
- 商品咨询 (Product Inquiry)
- 退款退货 (Refund/Return)
- 售后 (After-sales)
- 投诉 (Complaint)
- 人工 (Human Agent)
- 闲聊 (Chitchat)
- 其他 (Other)

### Knowledge Pipeline

```
Markdown Docs
  ↓
Parse & Chunk (by content_type: faq/policy/manual)
  ↓
Write to MySQL (status=pending)
  ↓
Embed API Call
  ↓
Write to Milvus + Update MySQL (status=done)
  ↓
User Query → Vector Search → Optional Rerank → Evidence
```

**Content Types:**
- `faq`: Q&A pairs
- `policy`: Policy clauses with section paths
- `manual`: Instructional content

### Quality Loop

```
Collect Low-Confidence Questions
  ↓
Manual Review
  ↓
Knowledge Mining → LLM Extract Q&A
  ↓
Staging Review → Approve/Reject
  ↓
Publish to KB → Auto-vectorize
  ↓
Higher Confidence on Similar Questions
```

---

## 📈 Key Design Decisions

Based on git commit history, here are the major architectural choices:

1. **LangGraph for Orchestration** (Ch05-Ch06)
   - Stateful conversation flow with checkpoints
   - Resumable execution after interrupts (ticket confirmation)
   - Visual graph structure for debugging

2. **Unified Tool System** (Ch08)
   - Registry-based tool discovery (local + MCP)
   - Standardized execution engine with timeout/retry
   - Complete audit trail with replay capability
   - Tool identity context for permission isolation

3. **RAG with Confidence Gating** (Ch03-Ch04)
   - Evidence sufficiency assessment before answering
   - Configurable confidence threshold
   - Refusal when evidence is insufficient

4. **Rolling Conversation Summary** (Ch07)
   - Automatic summarization at configurable intervals
   - Summary-aware intent recognition
   - Reduces context window usage

5. **Intent-Based Cost Attribution** (Ch09)
   - Track token usage by conversation intent
   - Enables business-level cost optimization
   - Identifies high-cost interaction patterns

6. **MCP Protocol Integration** (Ch08)
   - Standard protocol for external tools
   - HTTP transport with streaming support
   - Runtime discovery and error handling

---

## 🤝 Contributing

This project is primarily for learning and demonstration. External contributions are not currently open.

For questions or suggestions, please submit an Issue.

---

## 🙏 Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Milvus](https://milvus.io/)
- [OpenAI](https://openai.com/)
- [Langfuse](https://langfuse.com/)

---

## 📮 Contact

For issues, provide feedback through GitHub Issues.

## License

This project is released under the [MIT License](LICENSE). Runtime data, model weights, local test files, and `.env` are not included in the public repository.
