"""只读库存接口：一次性内存 SQLite 和临时材料，不调用模型或 Milvus。"""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.conftest import ADMIN_HEADERS
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import kb
from app.core import trusted_sources
from app.db import knowledge_repo, staging_repo
from app.db import database as db
from app.db.models import Base, QaExtractionStaging


@asynccontextmanager
async def database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionLocal", factory)
    try:
        yield factory
    finally:
        await engine.dispose()


def client():
    app = FastAPI()
    app.include_router(kb.router)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS)


def test_candidate_full_answer_all_counts_and_source_boundaries(monkeypatch, tmp_path):
    answer = "可信退货条件。" * 35
    (tmp_path / "returns-policy.md").write_text("# 条件\n" + answer, encoding="utf-8")
    (tmp_path / "after-sales-manual.md").mkdir()
    monkeypatch.setattr(trusted_sources, "KB_DIR", tmp_path)

    async def run():
        async with database(monkeypatch) as factory:
            async with factory() as session:
                states = ["extracted", "kept", "discarded", "approved", "rejected", "kept", "kept", "kept", "kept"]
                refs = ["returns-policy.md", "returns-policy.md", None, "returns-policy.md", "../outside.md",
                        "product-faq.md", "after-sales-manual.md", "returns-policy.md", "returns-policy.md"]
                session.add_all([QaExtractionStaging(
                    id=i, question="如何退货" if i != 9 else "订单 ORD-123 如何退货", answer=answer if i != 8 else "自行编写的答案",
                    status=state, source_ref=ref, batch_no="B" if i > 5 else "A",
                ) for i, (state, ref) in enumerate(zip(states, refs), 1)])
                await session.commit()
            async with client() as api:
                response = (await api.get("/api/kb/staging?limit=1")).json()
                assert response["stats"]["counts"] == {"extracted": 1, "kept": 5, "discarded": 1, "approved": 1, "rejected": 1}
                assert response["stats"]["total"] == 9 and response["stats"]["batches"] == 2
                assert len(response["rows"]["kept"]) == 1
                assert len(response["rows"]["kept"][0]["answer"]) == 160
            # 当前没有 staging 详情/材料 HTTP 接口，完整记录和来源校验使用现存仓储及校验器。
            rows = {row.id: row for row in await staging_repo.list_staging_by_ids(list(range(1, 10)))}
            detail = rows[2]
            assert detail.answer == answer and detail.status == "kept"
            digest = trusted_sources.validate_review_source(detail.question, detail.answer, detail.source_ref)
            assert len(digest) == 64
            for row_id, error in ((3, ValueError), (5, ValueError), (6, FileNotFoundError), (7, OSError)):
                row = rows[row_id]
                with pytest.raises(error):
                    trusted_sources.validate_review_source(row.question, row.answer, row.source_ref)
            with pytest.raises(ValueError, match="连续原文"):
                trusted_sources.validate_review_source(rows[8].question, rows[8].answer, rows[8].source_ref)
            with pytest.raises(ValueError, match="脱敏"):
                trusted_sources.validate_review_source(rows[9].question, rows[9].answer, rows[9].source_ref)
            assert await staging_repo.list_staging_by_ids([999]) == []
            assert len(await staging_repo.list_staging_by_status("kept")) == 5
            assert (await knowledge_repo.knowledge_stats())["total"] == 0
    asyncio.run(run())


def test_staging_unavailable_stats_is_sanitized(monkeypatch):
    monkeypatch.setattr(staging_repo, "staging_stats", AsyncMock(side_effect=RuntimeError("offline")))

    async def run():
        async with client() as api:
            response = await api.get("/api/kb/staging")
            assert response.status_code == 503 and "offline" not in response.text
    asyncio.run(run())


def test_bounded_parameters_and_unavailable_queries(monkeypatch):
    monkeypatch.setattr(staging_repo, "staging_stats", AsyncMock(return_value={}))
    monkeypatch.setattr(staging_repo, "list_staging_by_status", AsyncMock(return_value=[]))

    async def run():
        async with client() as api:
            for limit in (0, 101):
                assert (await api.get("/api/kb/staging", params={"limit": limit})).status_code == 422
    asyncio.run(run())


def test_preview_then_ingest_original_without_vectorization(monkeypatch):
    """一次性 SQLite 验证预览不写库、录入 pending、重复跳过；禁止外部向量化。"""
    vectorize = AsyncMock(side_effect=AssertionError("本测试不允许调用嵌入或 Milvus"))
    monkeypatch.setattr(kb.dualwrite, "vectorize_pending", vectorize)
    monkeypatch.setattr(kb, "milvus_state", AsyncMock(return_value={"online": False, "count": None}))

    async def run():
        async with database(monkeypatch):
            text = "# 测试材料\n\n## 原文条件\n这是一次性测试正文，只存原文。\n\n## 限制说明\n这是另一段测试内容，不用于实际客服。"
            payload = {"text": text, "content_type": "policy"}
            async with client() as api:
                preview = await api.post("/api/kb/preview", json=payload)
                assert preview.status_code == 200
                before = preview.json()
                assert before["total"] >= 1 and before["duplicates"] == 0 and before["dedup_known"]
                assert before["chunks"][0]["seq"] == 1
                assert before["chunks"][0]["chars"] == len(before["chunks"][0]["answer"])
                assert (await knowledge_repo.knowledge_stats())["total"] == 0

                response = await api.post("/api/kb/ingest", json={**payload, "vectorize": False})
                assert response.status_code == 200
                saved = response.json()
                assert saved["inserted"] == before["total"] and saved["skipped"] == 0
                assert len(saved["ids"]) == saved["inserted"] and saved["vectorized"] is None
                assert saved["chunk_stats"]["pending"] == saved["inserted"]
                pending = {row.id: row for row in await knowledge_repo.list_pending_chunks()}
                for chunk_id in saved["ids"]:
                    detail = pending[chunk_id]
                    assert detail.vectorize_status == "pending" and detail.vector_id is None

                repeated = (await api.post("/api/kb/ingest", json={**payload, "vectorize": False})).json()
                assert repeated["inserted"] == 0 and repeated["skipped"] == before["total"]
                assert repeated["ids"] == [] and repeated["vectorized"] is None
                after = (await api.post("/api/kb/preview", json=payload)).json()
                assert after["duplicates"] == before["total"]
                assert (await knowledge_repo.knowledge_stats())["total"] == before["total"]
                for invalid in ("", "# 只有标题", "x" * 40001):
                    assert (await api.post("/api/kb/ingest", json={"text": invalid, "vectorize": False})).status_code == 400
                assert (await knowledge_repo.knowledge_stats())["total"] == before["total"]
    asyncio.run(run())
    vectorize.assert_not_awaited()
