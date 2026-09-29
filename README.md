# AI Customer Service Platform

> Enterprise-grade AI customer service system for e-commerce · Dialogue Management, Knowledge Q&A, Business Processing & Quality Operations

[简体中文](./README.zh-CN.md) | English

This is a complete e-commerce AI customer service system built with **FastAPI + LangGraph + MySQL + Milvus** tech stack. The system supports natural language conversations, knowledge base retrieval, order queries, ticket processing, and provides comprehensive knowledge operations and quality monitoring capabilities.

## ✨ Key Features

### 🤖 Intelligent Dialogue
- Streaming responses for real-time interaction
- Multi-turn conversation context management
- Intent recognition and intelligent routing
- Conversation summarization and history compression

### 📚 Knowledge Q&A
- Vector retrieval with optional reranking
- Automatic evidence sufficiency assessment
- Query decomposition and multi-path retrieval
- Knowledge base review and publish workflow

### 🛠️ Business Tools
- Order queries (with permission isolation)
- Ticket creation and confirmation workflow
- MCP protocol integration for external services (logistics, after-sales)
- Tool invocation audit and replay

### 📊 Quality Loop
- Low-confidence question collection
- User feedback management
- Execution tracing and observability
- Model usage statistics (by intent)
- 17-class multi-label topic classifier

### 🔧 Developer Friendly
- Comprehensive Chinese code comments
- Unit and integration tests
- One-click local development environment
- Optional Langfuse observability integration

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
| **Conversation** | LangGraph + LangChain |
| **Data Storage** | MySQL (SQLAlchemy + Alembic) + SQLite (checkpoints) |
| **Vector Search** | Milvus + OpenAI-compatible Embedding API |
| **LLM** | OpenAI-compatible Chat API |
| **Tool Integration** | MCP (Model Context Protocol) |
| **Observability** | Local tracing + Optional Langfuse |
| **Topic Classification** | PyTorch + Transformers + ONNX Runtime |
| **Frontend** | Native HTML/CSS/JavaScript |

---

## 📁 Project Structure

```
智能客服/
├── app/                      # Application directory
│   ├── api/                  # FastAPI routes
│   │   ├── chat.py           # Basic chat interface
│   │   ├── graph_chat.py     # LangGraph chat interface
│   │   ├── conversations.py  # Conversation management
│   │   ├── knowledge.py      # Knowledge retrieval & eval
│   │   ├── observability.py  # Execution tracing
│   │   ├── feedback.py       # User feedback
│   │   ├── review.py         # Knowledge review
│   │   ├── topics.py         # Topic classification
│   │   └── acceptance.py     # Classifier acceptance
│   ├── core/                 # Core business logic
│   │   ├── llm.py            # LLM client
│   │   ├── embeddings.py     # Vectorization
│   │   ├── retrieval.py      # Knowledge retrieval
│   │   ├── rerank.py         # Reranking
│   │   ├── intent.py         # Intent recognition
│   │   ├── evidence.py       # Evidence assessment
│   │   ├── confidence.py     # Confidence scoring
│   │   ├── coref.py          # Coreference resolution
│   │   ├── summarizer.py     # Conversation summarization
│   │   └── observability.py  # Observability tracing
│   ├── graph/                # LangGraph conversation graph
│   │   ├── state.py          # State definition
│   │   ├── nodes.py          # Node implementation
│   │   ├── routing.py        # Routing decisions
│   │   ├── build.py          # Graph construction
│   │   ├── runtime.py        # Runtime
│   │   └── checkpoint.py     # Checkpoint management
│   ├── tools/                # Tool system
│   │   ├── registry.py       # Tool registry
│   │   ├── engine.py         # Tool execution engine
│   │   ├── order_tools.py    # Order query tools
│   │   ├── ticket_tools.py   # Ticket creation tools
│   │   ├── knowledge_tools.py# Knowledge retrieval tools
│   │   ├── mcp_client.py     # MCP client
│   │   └── audit.py          # Tool audit
│   ├── kb/                   # Knowledge base management
│   │   ├── documents.py      # Document parsing
│   │   ├── chunking.py       # Document chunking
│   │   ├── dualwrite.py      # Dual-write (MySQL + Milvus)
│   │   ├── milvus_client.py  # Milvus client
│   │   ├── mining.py         # Knowledge mining
│   │   └── review_publish.py # Review and publish
│   ├── db/                   # Database layer
│   │   ├── models.py         # SQLAlchemy models
│   │   ├── repository.py     # Data access layer
│   │   └── database.py       # Database connection
│   ├── static/               # Static assets (HTML/CSS/JS)
│   ├── schemas/              # Pydantic data models
│   ├── config.py             # Configuration management
│   └── main.py               # Application entry
├── data/
│   ├── kb/                   # Sample knowledge base materials
│   └── eval/                 # Evaluation datasets
├── migrations/               # Alembic database migrations
├── scripts/                  # Script tools
│   ├── tasks.py              # Unified task entry
│   ├── build_kb.py           # Build knowledge base
│   ├── vectorize_kb.py       # Vectorization
│   ├── eval_ch04.py          # RAG evaluation
│   └── ch10/                 # Topic classifier related
├── tests/                    # Test cases
├── .env.example              # Environment variables template
├── docker-compose.yml        # Docker service orchestration
├── pyproject.toml            # Project dependencies
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **uv** ([Installation Guide](https://docs.astral.sh/uv/))
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

Edit `.env` file with at least the following:

```env
# LLM Configuration
CHAT_MODEL=gpt-4o-mini
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=sk-...

# Embedding Configuration
EMBED_MODEL=text-embedding-3-small
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=sk-...

# Database Configuration (keep default when using docker-compose)
HANDWRITTEN_DATABASE_URL=mysql+asyncmy://root:root@127.0.0.1:3308/minihelp_complete

# Milvus Configuration
MILVUS_URI=http://127.0.0.1:19530
```

> ⚠️ **Security**: Do not commit `.env` files with real credentials to version control

### 3. Start Data Services

```bash
# Start MySQL and Milvus
docker compose up -d mysql etcd minio milvus

# Check service status
docker compose ps

# Run database migrations
uv run alembic upgrade head
```

### 4. Initialize Knowledge Base

```bash
# Preview chunking results (no write)
uv run python -m scripts.tasks kb-preview

# Write sample materials to MySQL
uv run python -m scripts.tasks kb-build

# Vectorize and write to Milvus
uv run python -m scripts.tasks kb-vectorize
```

### 5. Start Application

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Access the application at: **http://127.0.0.1:8000**

---

## 📱 Feature Pages

| Page | Route | Description |
|------|-------|-------------|
| 🏠 **Chat** | `/` | AI customer service chat interface |
| 🎛️ **Admin** | `/admin` | System management overview |
| 📚 **Knowledge Base** | `/kb` | Knowledge preview, entry, retrieval test |
| ✅ **Review** | `/review` | Pending knowledge review list |
| 📊 **Observability** | `/observability` | Trace records and model usage |
| 🏷️ **Topics** | `/topics` | Question classification statistics |
| 🔬 **RAG Eval** | `/rag-eval` | Retrieval quality assessment |
| 🎯 **Acceptance** | `/acceptance` | Classifier performance metrics |
| 📖 **API Docs** | `/docs` | FastAPI auto-generated docs |

---

## 🧪 Topic Classifier (Optional)

The topic classifier performs 17-class multi-label classification on user questions, supporting question distribution analysis and error case diagnosis.

### Training Workflow

```bash
# Install ML dependencies
uv sync --group dev --group ml

# 1. Prepare golden labeled set
uv run --group ml python -m scripts.tasks ch10-golden

# 2. Generate training corpus
uv run --group ml python -m scripts.tasks ch10-corpus

# 3. Build dataset
uv run --group ml python -m scripts.tasks ch10-dataset

# 4. Train model
uv run --group ml python -m scripts.tasks ch10-train

# 5. Evaluate model
uv run --group ml python -m scripts.tasks ch10-eval

# 6. Export to ONNX
uv run --group ml python -m scripts.tasks ch10-export

# 7. Start classification service (listens on port 8110)
uv run --group ml python -m scripts.tasks classifier-up
```

> 📝 **Note**: Training requires compatible Chinese RoBERTa-wwm-ext base weights in `data/ch10/pretrained/` directory.

---

## 🔧 Development Guide

### Run Tests

```bash
# Run all tests
uv run pytest tests -v

# Run specific tests
uv run pytest tests/test_ch06_integration.py -v

# Skip frontend tests
uv run pytest tests -q --ignore=tests/test_ch05_frontend.py --ignore=tests/test_ch06_frontend.py
```

### Database Migrations

```bash
# Create new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback migration
uv run alembic downgrade -1
```

### Knowledge Base Management

```bash
# Unified task entry
uv run python -m scripts.tasks

# Available tasks:
# kb-preview       Preview chunking
# kb-build         Build knowledge base
# kb-vectorize     Vectorization
# kb-review        Review interface
```

### Optional Integrations

**Enable Langfuse Observability**:
```bash
# Start local Langfuse (optional)
docker compose -f docker-compose.langfuse.yml up -d

# Configure in .env
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=http://127.0.0.1:3000
```

**Enable MCP Tools**:
```bash
# Configure MCP service URLs in .env
MCP_LOGISTICS_URL=http://127.0.0.1:8100
MCP_AFTERSALES_URL=http://127.0.0.1:8101
```

---

## 📊 Database Schema

| Table | Purpose |
|-------|---------|
| `conversations` | Conversation records |
| `messages` | Message history |
| `tickets` | Ticket records |
| `knowledge_chunks` | Knowledge chunks (pending/done) |
| `qa_extraction_staging` | Mined candidate knowledge |
| `reviews` | Knowledge review queue |
| `low_confidence_questions` | Low confidence questions |
| `user_feedback` | User feedback |
| `tool_audit_logs` | Tool invocation audit |
| `trace_spans` | Execution trace records |
| `topic_classifications` | Topic classification results |

---

## 🔍 Core Workflows

### Conversation Flow

```
User Input
  ↓
Intent Recognition ──→ Human/Chitchat ──→ Direct Reply
  ↓
  ├─→ Product Inquiry ──→ Knowledge Retrieval ──→ Evidence Assessment ──→ Generate Answer
  ├─→ Order Query ──→ Invoke Order Tool ──→ Return Results
  ├─→ Ticket Creation ──→ Confirmation Flow ──→ Create Ticket
  └─→ Logistics/After-sales ──→ MCP Tools ──→ External Services
```

### Knowledge Base Flow

```
Markdown Documents
  ↓
Document Parsing & Chunking
  ↓
Write to MySQL (pending)
  ↓
Call Embedding API
  ↓
Write to Milvus + Update Status (done)
  ↓
User Query → Vector Retrieval → Optional Rerank → Return Evidence
```

### Quality Loop

```
Low Confidence Question Collection
  ↓
Manual Review
  ↓
Knowledge Mining → Generate Candidate Knowledge
  ↓
Review & Publish → Add to Knowledge Base
  ↓
Similar Question Encountered → High Confidence Answer
```

---
## 🤝 Contributing
This project is primarily for learning and demonstration purposes. External contributions are not currently open. For questions or suggestions, please submit an Issue.
## 🙏 Acknowledgments
- [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Milvus](https://milvus.io/)
- [OpenAI](https://openai.com/)


## 📮 Contact

For issues, please provide feedback through GitHub Issues.
