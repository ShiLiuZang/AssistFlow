"""
测试知识库双写恢复机制
验证部分构建时的ID复用、邻居链修复和向量化断点续传功能
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import repository
from app.db.models import Base, KnowledgeChunk
from app.kb.documents import Chunk
from app.kb import dualwrite


def test_partial_build_reuses_ids_and_repairs_neighbors(monkeypatch):
    """测试部分构建场景：已有数据复用ID，并正确修复前后邻居链"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    class LocalSession:
        async def __aenter__(self):
            self.session = Session(engine, expire_on_commit=False)
            return self
        async def __aexit__(self, *args):
            self.session.close()
        async def scalars(self, statement):
            return self.session.scalars(statement)
        def add(self, row):
            self.session.add(row)
        async def flush(self):
            self.session.flush()
        async def commit(self):
            self.session.commit()
    monkeypatch.setattr(repository, "SessionLocal", LocalSession)
    chunks = [Chunk("A", "Q", answer, "A / Q", "faq") for answer in ["one", "two"]]
    first = asyncio.run(dualwrite.write_pending(chunks[:1]))
    all_ids = asyncio.run(dualwrite.write_pending(chunks))
    assert all_ids[0] == first[0]
    assert asyncio.run(dualwrite.write_pending(chunks)) == all_ids
    with Session(engine) as session:
        rows = list(session.scalars(select(KnowledgeChunk).order_by(KnowledgeChunk.id)))
        assert len(rows) == 2
        assert rows[0].next_chunk_id == rows[1].id
        assert rows[1].prev_chunk_id == rows[0].id


def test_second_batch_failure_then_resume(monkeypatch):
    """测试向量化批次失败后恢复：第二批失败，重跑后只处理未完成的记录"""
    rows = [SimpleNamespace(id=i, category="A", questions="Q", answer="text",
                            section_path="A/Q", content_type="faq", vectorize_status="pending")
            for i in range(1, 4)]
    async def pending():
        return [r for r in rows if r.vectorize_status == "pending"]
    async def mark(id, vector_id):
        rows[id - 1].vectorize_status = "done"
    async def acall(fn):
        return fn()
    stored = {}
    monkeypatch.setattr(repository, "list_pending_chunks", pending)
    monkeypatch.setattr(repository, "mark_chunk_vectorized", mark)
    monkeypatch.setattr(dualwrite.milvus_client, "acall", acall)
    monkeypatch.setattr(dualwrite.milvus_client, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(dualwrite.milvus_client, "flush", lambda *a, **k: None)
    monkeypatch.setattr(dualwrite.milvus_client, "upsert_vectors",
                        lambda client, batch, **kw: stored.update({r["id"]: r for r in batch}))
    embed = AsyncMock(side_effect=[[[0.] * 1024] * 2, RuntimeError("batch two")])
    monkeypatch.setattr(dualwrite.embeddings, "embed_texts", embed)
    with pytest.raises(RuntimeError):
        asyncio.run(dualwrite.vectorize_pending(client=object(), batch_size=2))
    assert [r.vectorize_status for r in rows] == ["done", "done", "pending"]
    embed.side_effect = None
    embed.return_value = [[0.] * 1024]
    assert asyncio.run(dualwrite.vectorize_pending(client=object(), batch_size=2)) == 1
    assert set(stored) == {1, 2, 3}
    assert asyncio.run(dualwrite.vectorize_pending(client=object())) == 0
