"""
测试主图的交接和任务生命周期
覆盖摘要加载、后台任务取消和等待机制
"""
import asyncio
from unittest.mock import patch

from langchain_core.messages import AIMessage
from sqlalchemy import update

from app.api import graph_chat
from app.core import summarizer
from app.db import conversation_repo
from app.db import database as db
from app.db.models import Conversation
from tests.test_graph_flow import chat, database, runtime, services


def test_next_turn_loads_saved_summary(monkeypatch):
    """测试下一轮加载摘要：从数据库读取已保存的摘要并传递给agent"""
    async def run():

        with patch.object(graph_chat, "schedule_persisted_summary", return_value=True):
            async with database(monkeypatch) as conversation_id:
                service = services([
                    AIMessage(content="第一轮回答"),
                    AIMessage(content="第二轮回答"),
                ])
                graph = runtime(service)

                first = await chat(graph, conversation_id, "第一轮问题")
                assert '"event": "done"' in "".join(first)

                rows = await conversation_repo.list_messages(conversation_id)
                boundary = max(
                    row.id for row in rows
                    if row.role in ("user", "assistant", "tool")
                )
                async with db.SessionLocal() as session, session.begin():
                    await session.execute(
                        update(Conversation)
                        .where(Conversation.id == conversation_id)
                        .values(
                            summary_text="用户第一轮诉求",
                            summary_upto=boundary,
                            summary_version=1,
                        )
                    )

                second = await chat(graph, conversation_id, "第二轮问题")
                assert '"event": "done"' in "".join(second)
                assert service.agent.await_args.kwargs["summary_text"] == "用户第一轮诉求"
                assert service.agent.await_args.kwargs["covered_count"] == 2

    asyncio.run(run())


def test_shutdown_cancels_and_waits_for_active_summary(monkeypatch):
    """测试关闭流程：取消活跃的摘要任务并等待完成"""
    async def run():
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def wait_forever(*_args, **_kwargs):
            started.set()
            try:
                await asyncio.Future()
            finally:
                await asyncio.sleep(0)
                stopped.set()

        monkeypatch.setattr(summarizer, "_running", {})
        monkeypatch.setattr(summarizer, "update_persisted_summary", wait_forever)
        try:
            assert summarizer.schedule_persisted_summary("u1", 1, wait_forever)
            await asyncio.wait_for(started.wait(), timeout=1)
            task = summarizer._running[("u1", 1)]
            assert not task.done()
            assert not stopped.is_set()

            await asyncio.wait_for(summarizer.close_persisted_summaries(), timeout=1)
            assert task.done()
            assert task.cancelled()
            assert stopped.is_set()
            assert summarizer._running == {}
        finally:
            await summarizer.close_persisted_summaries()

    asyncio.run(run())
