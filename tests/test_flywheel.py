"""
测试飞轮流程的归并、审核、发布和报表
覆盖问题归一化、合并去重、审核权限和可信来源验证
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.review import router as review_router
from app.core.flywheel import process_pending
from app.core.trusted_sources import validate_review_source
from app.db import repository
from app.kb.review_publish import publish_review
from tests.test_graph_flow import database


ANSWER = "无理由退货的退回运费由买家承担"
SOURCE = "returns-policy.md"


def test_normalization_idempotent_and_rejects_unoffered_match(monkeypatch):
    """测试归一化幂等性：重复运行不重复创建，拒绝未提供的匹配ID"""
    async def run():
        async with database(monkeypatch) as cid:
            for n in (1, 2):
                message_id = f"msg_{cid}_p{n}"
                await repository.save_turn("u1", str(cid), message_id, f"p{n}", "退货运费谁出", [])
                await repository.capture_low_confidence("u1", str(cid), message_id, "user_feedback")

            async def normalize(question, candidates):
                return {"question": "退货运费谁承担", "suggestion": "待审核", "matched_id": candidates[0]["id"] if candidates else None}

            stats = await process_pending(normalize)
            assert (stats["created"], stats["merged"], stats["skipped"]) == (1, 1, 0)
            rows = await repository.list_review_queue()
            assert len(rows) == 1 and rows[0]["occurrence_count"] == 2
            assert (await process_pending(normalize))["created"] == 0

            message_id = f"msg_{cid}_p3"
            await repository.save_turn("u1", str(cid), message_id, "p3", "质量问题退货运费谁出", [])
            await repository.capture_low_confidence("u1", str(cid), message_id, "user_feedback")
            async def invented(question, candidates):
                return {"question": question, "suggestion": "", "matched_id": 999999}
            result = await process_pending(invented)
            assert result["skipped"] == 1
            assert len(await repository.list_unmatched_questions()) == 1
            assert (await repository.list_review_queue())[0]["occurrence_count"] == 2

    asyncio.run(run())


def test_review_without_token_and_same_chunk_recovery(monkeypatch):
    """测试审核流程：无token验证和相同块恢复"""
    async def run():
        async with database(monkeypatch) as cid:
            await repository.save_turn("u1", str(cid), "msg_1_r1", "r1", "退货运费谁出", [])
            pool_id = await repository.capture_low_confidence("u1", str(cid), "msg_1_r1", "user_feedback")
            review_id, _ = await repository.merge_question(pool_id, "退货运费谁出", "所有退货免运费", None, set())
            app = FastAPI()
            app.include_router(review_router)

            index = SimpleNamespace(
                upsert=AsyncMock(),
                visible=AsyncMock(side_effect=[False, True, True]),
            )

            async def publish(review_id):
                return await publish_review(review_id, index=index)

            monkeypatch.setattr("app.api.review.publish_review", publish)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
                queue = await api.get("/api/review/queue")
                assert queue.status_code == 200
                assert [row["id"] for row in queue.json()["items"]] == [review_id]
                payload = {"approved_answer": "所有退货免运费", "source_ref": SOURCE}
                invalid = await api.post(f"/api/review/{review_id}/approve", json=payload)
                assert invalid.status_code == 422
                assert (await repository.get_review_detail(review_id))["status"] == "pending"
                assert (await repository.knowledge_stats())["total"] == 0
                index.upsert.assert_not_awaited()

                payload["approved_answer"] = ANSWER
                failed = await api.post(f"/api/review/{review_id}/approve", json=payload)
                assert failed.status_code == 202
                frozen = failed.json()
                assert frozen["status"] == "publishing"
                assert frozen["answer"] == ANSWER
                assert frozen["source_ref"] == SOURCE
                assert frozen["source_digest"] == validate_review_source("退货运费谁出", ANSWER, SOURCE)
                assert frozen["publish_error"] == "RuntimeError"
                pending = await repository.list_pending_chunks()
                assert len(pending) == 1
                chunk_id = pending[0].id
                assert pending[0].answer == ANSWER
                assert pending[0].vectorize_status == "pending"
                assert pending[0].vector_id is None

                for _ in range(2):
                    recovered = await api.post(f"/api/review/{review_id}/publish")
                    assert recovered.status_code == 200
                    assert recovered.json()["status"] == "approved"
                    assert recovered.json()["chunk_id"] == chunk_id
                    assert recovered.json()["publish_error"] is None
                    stats = await repository.knowledge_stats()
                    assert (stats["total"], stats["pending"], stats["done"]) == (1, 0, 1)
                assert index.upsert.await_count == index.visible.await_count == 3
                assert [call.args[0]["id"] for call in index.upsert.await_args_list] == [chunk_id] * 3
                assert [call.args[0]["id"] for call in index.visible.await_args_list] == [chunk_id] * 3

    asyncio.run(run())
