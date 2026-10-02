"""scripts.mine_kb：对话挖知识作业（内存 SQLite + 替身挖掘函数，不调模型、不连 MySQL）。"""
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, Conversation, KnowledgeChunk, Message, QaExtractionStaging
from scripts import mine_kb

QUOTE = "自签收之日起 7 天内,商品完好、不影响二次销售的,支持无理由退货。"


def candidate(question="无理由退货有几天？", quote=QUOTE, source_file="returns-policy.md"):
    return {"question": question, "quote": quote, "source_file": source_file}


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def add_conversation(factory, *messages, user_id="u1"):
    async with factory() as session:
        conversation = Conversation(user_id=user_id)
        session.add(conversation)
        await session.flush()
        for role, content in messages:
            session.add(Message(conversation_id=conversation.id, role=role, content=content))
        await session.commit()
        return conversation.id


async def staged(factory):
    async with factory() as session:
        return list(await session.scalars(select(QaExtractionStaging).order_by(QaExtractionStaging.id)))


class FakeMiner:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def __call__(self, dialogue):
        self.calls.append(dialogue)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class TestSanitize:
    def test_masks_identifiers(self):
        rows = [SimpleNamespace(role="user", content="订单 ORD-1001，手机 13812345678")]
        content = mine_kb.sanitize_dialogue(rows)[0]["content"]
        assert "ORD-1001" not in content and "13812345678" not in content
        assert "[订单号]" in content and "[手机号]" in content

    def test_total_budget_and_blank_rows(self):
        rows = [SimpleNamespace(role="user", content=" "), *[SimpleNamespace(role="user", content="字" * 5000)] * 4]
        result = mine_kb.sanitize_dialogue(rows)
        assert [len(item["content"]) for item in result] == [4000, 4000, 4000]


class TestRunMining:
    async def test_invalid_candidate_rolls_back_batch(self, db):
        await add_conversation(db, ("user", "买了不想要能退吗"), ("assistant", "签收 7 天内可以退"))
        miner = FakeMiner([candidate(), candidate(question="编造的", quote="不存在的原文")])

        summary = await mine_kb.run_mining(db, miner)

        # 一个候选不合法时整批回滚，不留下半批数据，也不计入保留数
        assert summary["kept"] == 0 and summary["failed"] == 1
        assert await staged(db) == []

    async def test_writes_kept_and_dedups(self, db):
        async with db() as session:
            session.add(KnowledgeChunk(category="退货", questions="退货运费谁出", answer="买家承担"))
            await session.commit()
        await add_conversation(db, ("user", "能退吗"), ("assistant", "可以"))
        miner = FakeMiner([candidate(), candidate(question="退货运费谁出？")])

        summary = await mine_kb.run_mining(db, miner)

        rows = await staged(db)
        assert summary == {"conversations": 1, "kept": 1, "discarded": 1, "unchanged": 0, "failed": 0}
        assert [(row.question, row.status) for row in rows] == [("无理由退货有几天？", "kept"), ("退货运费谁出？", "discarded")]
        assert rows[0].batch_no.startswith("mine-")

    async def test_rerun_skips_same_batch(self, db):
        await add_conversation(db, ("user", "能退吗"), ("assistant", "可以"))
        await mine_kb.run_mining(db, FakeMiner([candidate()]))
        miner = FakeMiner()

        summary = await mine_kb.run_mining(db, miner)

        assert summary["unchanged"] == 1 and miner.calls == []
        assert len(await staged(db)) == 1

    async def test_skips_conversations_without_user_text(self, db):
        await add_conversation(db, ("assistant", "您好"))
        miner = FakeMiner()
        assert (await mine_kb.run_mining(db, miner))["conversations"] == 0
        assert miner.calls == []

    async def test_model_failure_counts_and_continues(self, db):
        await add_conversation(db, ("user", "a"), ("assistant", "b"))
        await add_conversation(db, ("user", "c"), ("assistant", "d"))
        miner = FakeMiner(RuntimeError("down"), [candidate()])

        summary = await mine_kb.run_mining(db, miner)

        assert summary["failed"] == 1 and summary["kept"] == 1
