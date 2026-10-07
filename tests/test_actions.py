"""
测试工单决策流的完整性
覆盖工具调用后的确认/取消流程、消息序列的正确性
"""
import asyncio
import json
import pytest

from app.api.actions import stream_ticket_decision
from app.api.graph_chat import restore_messages
from app.db import repository
from app.schemas.actions import ResumeTicketRequest
from tests.test_graph_flow import database, call, ticket_count, events


@pytest.mark.parametrize("confirmed", [True, False])
def test_ticket_decision_closes_tool_call_before_user_message(monkeypatch, confirmed):
    """测试工单确认流程：工具调用结果应在用户消息前插入"""
    async def run():
        async with database(monkeypatch) as cid:
            item = call("ticket-call-1")
            await repository.append_message(cid, "assistant", "", tool_calls=[item])
            request = ResumeTicketRequest(conversation_id=cid, user_id="u1", confirmed=confirmed)
            frames = [frame async for frame in stream_ticket_decision(request, item)]
            history = restore_messages(await repository.list_messages(cid))
            assert [message.type for message in history] == ["ai", "tool", "human", "ai"]
            assert history[1].tool_call_id == history[0].tool_calls[0]["id"]
            assert json.loads(history[1].content)["confirmed"] is confirmed
            assert await ticket_count() == int(confirmed)
            assert events(frames)[-1] == {"event": "done", "conversation_id": cid}
            assert frames[-1] == "data: [DONE]\n\n"
    asyncio.run(run())
