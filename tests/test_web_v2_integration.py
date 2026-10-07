"""V2 接口与挖掘连接验收：仅内存 SQLite、替身模型，不调用真实服务。"""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api.feedback import router as feedback_router
from app.api.review import router as review_router
from app.core.flywheel import process_pending
from app.db import conversation_repo, flywheel_repo
from app.db import database as db
from app.db.models import Base, LowConfidenceQuestion, Review, Turn


@asynccontextmanager
async def isolated_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionLocal", factory)
    try:
        yield factory
    finally:
        await engine.dispose()


async def stored_counts(factory):
    """已删除 /review/stats；直接核对当前持久化模型的状态。"""
    async with factory() as session:
        return {
            "saved_turns": await session.scalar(select(func.count()).select_from(Turn)),
            "pool_total": await session.scalar(select(func.count()).select_from(LowConfidenceQuestion)),
            "unmerged": await session.scalar(select(func.count()).select_from(LowConfidenceQuestion).where(LowConfidenceQuestion.review_id.is_(None))),
            "reviews": dict((await session.execute(select(Review.status, func.count()).group_by(Review.status))).all()),
        }


def test_feedback_pool_merge_and_readonly_stats(monkeypatch):
    async def run():
        async with isolated_db(monkeypatch) as factory:
            cid = await conversation_repo.create_conversation("v2-test")
            await flywheel_repo.save_turn("v2-test", str(cid), "v2-test-message", "v2-test-request", "退货运费谁出", [])
            app = FastAPI()
            app.include_router(feedback_router)
            app.include_router(review_router)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                before = await stored_counts(factory)
                assert before == {"saved_turns": 1, "pool_total": 0, "unmerged": 0, "reviews": {}}
                body = {"user_id": "v2-test", "conversation_id": cid, "message_id": "v2-test-message", "rating": "down"}
                response = await client.post("/api/feedback", json=body)
                assert response.status_code == 200 and response.json()["pool_id"]
                assert (await client.post("/api/feedback", json=body)).json()["pool_id"] == response.json()["pool_id"]
                after = await stored_counts(factory)
                assert after["pool_total"] == after["unmerged"] == 1
                assert (await client.post("/api/feedback", json={**body, "user_id": "another"})).status_code == 404
                normalizer = AsyncMock(return_value={"question": "退货运费谁出", "suggestion": "待人工补充", "matched_id": None})
                assert (await process_pending(normalizer))["created"] == 1
                final = await stored_counts(factory)
                assert final["unmerged"] == 0 and final["reviews"] == {"pending": 1}
                queue = (await client.get("/api/review/queue")).json()
                assert len(queue["items"]) == 1
                assert queue["items"][0]["question"] == "退货运费谁出"
    asyncio.run(run())
