"""离线单元测试只使用占位模型配置，不依赖本机 .env。"""
import os
from unittest.mock import patch


for name, value in {
    "PYTHON_DOTENV_DISABLED": "1",
    "CHAT_MODEL": "test-model", "CHAT_BASE_URL": "http://127.0.0.1:1/v1",
    "CHAT_API_KEY": "test-placeholder", "EMBED_MODEL": "test-embed",
    "EMBED_BASE_URL": "http://127.0.0.1:1/v1", "EMBED_API_KEY": "test-placeholder",
    "MYSQL_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "MILVUS_URI": "http://127.0.0.1:1",
    "RERANK_BASE_URL": "http://127.0.0.1:1/v1", "RERANK_API_KEY": "test-placeholder",
    "MCP_LOGISTICS_URL": "", "MCP_AFTERSALES_URL": "",
    "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "", "LANGFUSE_BASE_URL": "",
    "ADMIN_TOKEN": "test-admin-placeholder", "AUTH_SECRET": "test-auth-placeholder",
}.items():
    os.environ[name] = value


# 初次导入只使用上述占位环境变量；临时 env 的配置测试仍使用真实读取器。
with patch("pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}):
    from app.core.auth import issue_visitor_token


ADMIN_HEADERS = {"Authorization": "Bearer test-admin-placeholder"}


def visitor_headers(user_id: str = "u1") -> dict[str, str]:
    token, _ = issue_visitor_token(user_id)
    return {"Authorization": f"Bearer {token}"}
