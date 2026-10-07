"""
测试数据契约的健壮性
覆盖embedding接口的错误处理、文档分块的内容完整性
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.core import embeddings
from app.kb.chunking import apply_sentence_overlap
from app.kb.documents import build_chunks


@pytest.mark.parametrize("indices", [[0], [0, 0], [0, 2], []])
def test_embedding_rejects_bad_indices(monkeypatch, indices):
    """测试embedding响应验证：拒绝索引不连续或数量不匹配的响应"""
    client = SimpleNamespace(embeddings=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
        data=[SimpleNamespace(index=i, embedding=[i]) for i in indices]))))
    monkeypatch.setattr(embeddings, "_client", lambda: client)
    with pytest.raises(ValueError):
        asyncio.run(embeddings.embed_texts(["A", "B"]))


def test_embedding_reorders_each_batch(monkeypatch):
    """测试embedding批处理重排序：确保返回顺序与输入一致"""
    async def create(**kw):
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[int(text)])
            for i, text in reversed(list(enumerate(kw["input"])))])
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    monkeypatch.setattr(embeddings, "_client", lambda: client)
    assert asyncio.run(embeddings.embed_texts([str(i) for i in range(12)])) == [[i] for i in range(12)]


def test_long_prose_and_mixed_table_preserve_content():
    """测试长文本与表格混合分块：内容不丢失，路径正确"""
    text = "# 政策\n## 时效\n" + "需要保留原包装。" * 100
    text += "\n\n| 项目 | 值 |\n| --- | --- |\n| A | 1 |\n| B | 2 |\n\n表后说明不能丢失。"
    chunks = build_chunks(text, "policy", chunk_size=80, table_max_rows=1)
    assert len(chunks) > 5
    tables = [c.answer for c in chunks if "| 项目 |" in c.answer]
    assert len(tables) == 2
    assert all("| --- |" in table for table in tables)
    assert any("表后说明不能丢失" in c.answer for c in chunks)
    assert all(c.section_path == "政策 / 时效" for c in chunks)
    assert apply_sentence_overlap(["完整句。", "下一句。"], 0) == ["完整句。", "下一句。"]
