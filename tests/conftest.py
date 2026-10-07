"""离线单元测试只使用占位模型配置，不依赖本机 .env。"""
import os


for name, value in {
    "CHAT_MODEL": "test-model", "CHAT_BASE_URL": "http://127.0.0.1:1/v1",
    "CHAT_API_KEY": "test-placeholder", "EMBED_MODEL": "test-embed",
    "EMBED_BASE_URL": "http://127.0.0.1:1/v1", "EMBED_API_KEY": "test-placeholder",
    "MYSQL_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "MILVUS_URI": "http://127.0.0.1:1",
    "RERANK_BASE_URL": "http://127.0.0.1:1/v1", "RERANK_API_KEY": "test-placeholder",
    "MCP_LOGISTICS_URL": "", "MCP_AFTERSALES_URL": "",
    "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "", "LANGFUSE_BASE_URL": "",
}.items():
    os.environ[name] = value
