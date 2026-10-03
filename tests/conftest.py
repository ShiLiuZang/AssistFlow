"""测试公共配置：在导入 app 之前注入固定配置，隔离真实的 LLM、Milvus、MySQL。"""
import os

# Settings 在模块导入时实例化，必填项必须先就位；
# 直接覆盖而非 setdefault，避免本地 .env 改变阈值导致测试结果漂移。
_TEST_ENV = {
    "CHAT_MODEL": "test-chat-model",
    "CHAT_BASE_URL": "http://llm.invalid/v1",
    "CHAT_API_KEY": "test-key",
    "EMBED_MODEL": "test-embed-model",
    "EMBED_BASE_URL": "http://embed.invalid/v1",
    "EMBED_API_KEY": "test-key",
    "RERANK_BASE_URL": "http://rerank.invalid/v1",
    "RERANK_API_KEY": "test-key",
    "RERANK_API_STYLE": "auto",
    "RECALL_TOP_K": "50",
    "RERANK_MIN_SCORE": "0.3",
    "EVIDENCE_MIN_CONFIDENCE": "0.5",
    "LANGFUSE_PUBLIC_KEY": "",
    "LANGFUSE_SECRET_KEY": "",
    "LANGFUSE_BASE_URL": "",
    "CHAT_THINKING": "disabled",
    "MILVUS_URI": "http://milvus.invalid:19530",
    "MILVUS_COLLECTION": "test_collection",
    "MCP_LOGISTICS_URL": "",
    "MCP_AFTERSALES_URL": "",
    "AUTH_SECRET": "test-auth-secret-" + "x" * 32,
    "CUSTOMER_TOKEN_SECRET": "test-customer-secret-" + "y" * 32,
    "AUTH_DEV_MODE": "false",
    "PDD_ENABLED": "false",
}
os.environ.update(_TEST_ENV)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """限流计数是进程级的，测试之间互不影响。"""
    from app.core import ratelimit

    ratelimit.limiter.reset()
    yield
    ratelimit.limiter.reset()


@pytest.fixture(autouse=True)
def _reset_observability():
    """每个测试结束后清空全局 trace sink 与 Langfuse 客户端。"""
    yield
    from app.core import observability

    observability.configure_trace_sink(None)
    observability.configure_langfuse(None)
