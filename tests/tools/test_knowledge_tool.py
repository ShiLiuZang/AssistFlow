"""app.tools.knowledge_tools：基础 Dense 检索工具（嵌入与 Milvus 为替身）。"""
import pytest

from app.kb import milvus_client
from app.tools import knowledge_tools


@pytest.fixture
def backend(monkeypatch):
    calls = []

    async def embed(query):
        calls.append(("embed", query))
        return backend.vector

    async def acall(work):
        return work()

    monkeypatch.setattr(knowledge_tools, "embed_query", embed)
    monkeypatch.setattr(milvus_client, "acall", acall)
    monkeypatch.setattr(milvus_client, "get_client", lambda: "client")
    monkeypatch.setattr(milvus_client, "ensure_collection", lambda client: calls.append(("ensure", client)))
    monkeypatch.setattr(milvus_client, "dense_search",
                        lambda client, vector, top_k: calls.append(("search", top_k)) or [{"id": 1}])
    backend.vector = [0.1] * milvus_client.DIM
    backend.calls = calls
    return backend


async def test_returns_evidence_with_instruction(backend):
    result = await knowledge_tools.search_knowledge.ainvoke({"query": "退货"})
    assert result["evidence"] == [{"id": 1}]
    assert "无法确认" in result["instruction"]
    assert backend.calls == [("embed", "退货"), ("ensure", "client"), ("search", 5)]


async def test_rejects_wrong_dimension(backend):
    backend.vector = [0.1]
    with pytest.raises(ValueError, match="维度"):
        await knowledge_tools.search_knowledge.ainvoke({"query": "退货"})
    assert [c[0] for c in backend.calls] == ["embed"]
