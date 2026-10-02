"""app.core.persistent_summary：在临时 SQLite 上验证摘要的读取、乐观锁写回与冲突检测。"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.persistent_summary import PersistentSummaryStore, SummaryConflict
from app.core.summarizer import Summary
from app.db.models import Base, Conversation, Message

CALL = {"id": "c1", "name": "query_order", "args": {}}


@pytest.fixture
async def sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'summary.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[Conversation.__table__, Message.__table__]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(Conversation(id=1, user_id="u1", summary_text=None))
        session.add_all([
            Message(id=1, conversation_id=1, role="user", content="第一问"),
            Message(id=2, conversation_id=1, role="assistant", content=None, tool_calls=[CALL]),
            Message(id=3, conversation_id=1, role="tool", content="{}", tool_call_id="c1"),
            Message(id=4, conversation_id=1, role="assistant", content="第一答"),
            Message(id=5, conversation_id=1, role="system", content="不进摘要"),
            Message(id=6, conversation_id=1, role="user", content="第二问"),
            Message(id=7, conversation_id=1, role="assistant", content="第二答"),
            Message(id=8, conversation_id=1, role="user", content="第三问"),
            Message(id=9, conversation_id=1, role="assistant", content="第三答"),
        ])
    yield factory
    await engine.dispose()


async def conversation_row(factory):
    async with factory() as session:
        return await session.scalar(select(Conversation).where(Conversation.id == 1))


async def test_load_maps_roles_and_tool_calls(sessions):
    summary, version, messages = await PersistentSummaryStore(sessions).load(("u1", 1))

    assert (summary, version) == (Summary("", 0), 0)
    assert [m.id for m in messages] == [1, 2, 3, 4, 6, 7, 8, 9]
    assert [m.role for m in messages[:4]] == ["human", "ai", "tool", "ai"]
    assert (messages[1].content, messages[1].calls, messages[2].call_id) == ("", ("c1",), "c1")


async def test_load_checks_owner(sessions):
    with pytest.raises(ValueError, match="会话不存在"):
        await PersistentSummaryStore(sessions).load(("u2", 1))


async def test_update_writes_text_cursor_and_version(sessions):
    seen = []

    async def summarize(old_text, delta):
        seen.append((old_text, [m.id for m in delta]))
        return "用户查过订单"

    new = await PersistentSummaryStore(sessions).update(("u1", 1), summarize, keep=2)

    assert new == Summary("用户查过订单", 4)
    assert seen == [("", [1, 2, 3, 4])]
    row = await conversation_row(sessions)
    assert (row.summary_text, row.summary_upto, row.summary_version) == ("用户查过订单", 4, 1)


async def test_update_noop_below_threshold(sessions):
    async def summarize(old_text, delta):
        raise AssertionError("不应调用模型")

    store = PersistentSummaryStore(sessions)
    assert await store.update(("u1", 1), summarize, keep=2, threshold=5) == Summary("", 0)
    assert (await conversation_row(sessions)).summary_version == 0
    with pytest.raises(ValueError, match="threshold"):
        await store.update(("u1", 1), summarize, threshold=0)


async def test_concurrent_writer_causes_conflict(sessions):
    async def summarize(old_text, delta):
        async with sessions() as session, session.begin():
            row = await session.scalar(select(Conversation).where(Conversation.id == 1))
            row.summary_version += 1
        return "迟到的摘要"

    with pytest.raises(SummaryConflict):
        await PersistentSummaryStore(sessions).update(("u1", 1), summarize, keep=2)
    assert (await conversation_row(sessions)).summary_text is None


def test_defaults_to_project_session_factory():
    from app.db.database import SessionLocal

    assert PersistentSummaryStore().sessions is SessionLocal
