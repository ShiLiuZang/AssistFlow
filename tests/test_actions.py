"""
测试工单决策流的完整性
覆盖工具调用后的确认/取消流程、消息序列的正确性
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.api import actions, graph_chat
from app.api.actions import stream_ticket_decision
from app.api.graph_chat import restore_messages
from app.db import repository
from app.schemas.actions import ResumeTicketRequest
from tests.test_graph_flow import database, call, chat, runtime, services, ticket_count, events
from tests.test_order_select_resume import setup_runtime


@pytest.mark.parametrize("confirmed", [True, False])
def test_ticket_decision_resumes_graph_without_extra_dialog_messages(monkeypatch, confirmed):
    """确认/取消恢复图，仅保存决策和图消息；同一请求重试不重复建单。"""
    monkeypatch.setattr(actions, "schedule_graph_summary", Mock())

    async def run():
        async with database(monkeypatch) as cid:
            item = call("ticket-call-1")
            graph_runtime = runtime(services([
                AIMessage(content="", tool_calls=[item]), AIMessage(content="处理完成"),
            ]))
            initial = events(await chat(graph_runtime, cid))
            assert initial[-1]["event"] == "interrupt"
            request = ResumeTicketRequest(conversation_id=cid, user_id="u1", confirmed=confirmed,
                                          tool_call_id=item["id"])
            frames = [frame async for frame in stream_ticket_decision(request, item, graph_runtime)]
            records = await repository.list_messages(cid)
            history = restore_messages(records)
            assert [message.type for message in history] == ["human", "ai", "tool", "ai"]
            assert history[0].content == "建单"
            assert history[2].tool_call_id == history[1].tool_calls[0]["id"]
            assert json.loads(history[2].content)["confirmed"] is confirmed
            decisions = [record for record in records if record.role == "ticket_decision"]
            assert len(decisions) == 1
            assert json.loads(decisions[0].content)["confirmed"] is confirmed
            assert await ticket_count() == int(confirmed)
            assert events(frames)[-1] == {"event": "done", "conversation_id": cid}
            assert frames[-1] == "data: [DONE]\n\n"

            retry = [frame async for frame in stream_ticket_decision(request, item, graph_runtime)]
            assert retry == frames
            assert len(await repository.list_messages(cid)) == len(records)
            assert await ticket_count() == int(confirmed)
    asyncio.run(run())


@pytest.mark.parametrize("endpoint", ["resume", "pending"])
@pytest.mark.parametrize("runtime_present", [False, True])
def test_ticket_actions_require_runtime(monkeypatch, endpoint, runtime_present):
    """图运行时未挂载或为None时返回503，不再使用数据库消息恢复。"""
    monkeypatch.setattr(repository, "get_conversation", AsyncMock(return_value=object()))
    lookup = AsyncMock(side_effect=AssertionError("不应查询数据库待确认工单"))
    monkeypatch.setattr(repository, "list_messages", lookup)
    app = FastAPI()
    app.include_router(actions.router)
    if runtime_present:
        app.state.graph_runtime = None
    with TestClient(app) as client:
        if endpoint == "resume":
            response = client.post("/api/actions/resume", json={
                "conversation_id": 1, "user_id": "u1", "confirmed": True, "tool_call_id": "call-1",
            })
        else:
            response = client.get("/api/actions/pending", params={"conversation_id": 1, "user_id": "u1"})
    assert response.status_code == 503
    assert response.json() == {"detail": "图服务尚未就绪"}
    lookup.assert_not_awaited()


def test_resume_rejects_missing_call_id_before_lookup(monkeypatch):
    """HTTP请求缺少tool_call_id时返回422，不再从消息历史推断调用。"""
    owner = AsyncMock()
    lookup = AsyncMock()
    monkeypatch.setattr(repository, "get_conversation", owner)
    monkeypatch.setattr(repository, "list_messages", lookup)
    app = FastAPI()
    app.include_router(actions.router)
    app.state.graph_runtime = SimpleNamespace()
    with TestClient(app) as client:
        response = client.post("/api/actions/resume", json={
            "conversation_id": 1, "user_id": "u1", "confirmed": True,
        })
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "tool_call_id"]
    owner.assert_not_awaited()
    lookup.assert_not_awaited()


def test_pending_without_interrupt_ignores_unresolved_database_call(monkeypatch):
    """数据库存在未决工具调用时，无图中断仍返回None。"""
    async def run():
        async with database(monkeypatch) as cid:
            await repository.append_message(cid, "assistant", "", tool_calls=[call("call-1")])
            records = await repository.list_messages(cid)
            assert records[0].tool_calls == [call("call-1")]
            lookup = AsyncMock(side_effect=AssertionError("不应回退到数据库消息"))
            monkeypatch.setattr(repository, "list_messages", lookup)
            graph_runtime = runtime(services())
            request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph_runtime=graph_runtime)))
            assert await actions.pending_ticket(cid, "u1", request) is None
            lookup.assert_not_awaited()
    asyncio.run(run())


def test_ticket_decision_without_graph_interrupt_does_not_create_ticket(monkeypatch):
    """空图状态不能触发工单决策，即使数据库里有未决调用。"""
    scheduled = Mock()
    monkeypatch.setattr(actions, "schedule_graph_summary", scheduled)

    async def run():
        async with database(monkeypatch) as cid:
            item = call("call-1")
            await repository.append_message(cid, "assistant", "", tool_calls=[item])
            request = ResumeTicketRequest(conversation_id=cid, user_id="u1", confirmed=True,
                                          tool_call_id=item["id"])
            frames = [frame async for frame in stream_ticket_decision(request, item, runtime(services()))]
            assert frames[0].startswith("event: error\n")
            assert frames[-1] == "data: [DONE]\n\n"
            assert await ticket_count() == 0
            assert await repository.get_ticket_decision(cid, item["id"]) is None
            assert len(await repository.list_messages(cid)) == 1
    asyncio.run(run())
    scheduled.assert_not_called()


@pytest.mark.parametrize("confirmed", [True, False])
def test_ticket_retry_continues_graph_after_decision_was_saved(monkeypatch, confirmed):
    """决策保存后图执行失败，重试继续原轮次，不重复建单或追加对话。"""
    scheduled = Mock()
    monkeypatch.setattr(actions, "schedule_graph_summary", scheduled)

    async def run():
        async with database(monkeypatch) as cid:
            item = call("retry-call")
            service = services([
                AIMessage(content="", tool_calls=[item]),
                RuntimeError("test graph failure"),
                AIMessage(content="处理完成"),
            ])
            graph_runtime = runtime(service)
            assert events(await chat(graph_runtime, cid))[-1]["event"] == "interrupt"
            request = ResumeTicketRequest(
                conversation_id=cid, user_id="u1", confirmed=confirmed, tool_call_id=item["id"],
            )
            failed = [frame async for frame in stream_ticket_decision(request, item, graph_runtime)]
            assert failed[0].startswith("event: error\n")
            assert failed[-1] == "data: [DONE]\n\n"
            assert (await graph_runtime.get_state("u1", cid)).next == ("agent",)
            assert await graph_runtime.pending_interrupt("u1", cid) is None
            assert (await repository.get_ticket_decision(cid, item["id"]))["confirmed"] is confirmed
            assert await ticket_count() == int(confirmed)
            scheduled.assert_not_called()

            continued = AsyncMock(wraps=graph_runtime.continue_turn)
            monkeypatch.setattr(graph_runtime, "continue_turn", continued)
            frames = [frame async for frame in stream_ticket_decision(request, item, graph_runtime)]
            continued.assert_awaited_once_with("u1", cid)
            assert events(frames)[-1] == {"event": "done", "conversation_id": cid}
            assert frames[-1] == "data: [DONE]\n\n"
            assert not (await graph_runtime.get_state("u1", cid)).next
            assert await ticket_count() == int(confirmed)
            records = await repository.list_messages(cid)
            history = restore_messages(records)
            assert [message.type for message in history] == ["human", "ai", "tool", "ai"]
            assert history[2].tool_call_id == item["id"]
            assert len([record for record in records if record.role == "ticket_decision"]) == 1
            scheduled.assert_called_once_with("u1", cid)
    asyncio.run(run())


@pytest.mark.parametrize("kind, detail", [
    ("confirm_ticket", "请先确认或取消待处理工单"),
    ("select_order", "请先选择或取消待处理订单"),
    (None, None),
])
def test_graph_chat_precheck_uses_pending_graph_interrupt(monkeypatch, kind, detail):
    """工单和选单中断均阻止续聊；无中断进入 SSE 流，不扫描数据库消息。"""
    cid = 42
    if kind == "select_order":
        graph_runtime, _ = setup_runtime()
    else:
        graph_runtime = runtime(services([AIMessage(content="", tool_calls=[call("call-1")])]))
    if kind is not None:
        result = asyncio.run(graph_runtime.run_turn("建单", "u1", str(cid)))
        assert result["__interrupt__"][0].value["kind"] == kind

    monkeypatch.setattr(repository, "get_conversation", AsyncMock(return_value=SimpleNamespace(id=cid)))
    lookup = AsyncMock(side_effect=AssertionError("预检不应从数据库消息推断中断"))
    monkeypatch.setattr(repository, "list_messages", lookup)
    started = Mock()

    async def stream(request, conversation_id, current_runtime):
        started(request.user_id, conversation_id, current_runtime)
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(graph_chat, "stream_graph_chat", stream)
    app = FastAPI()
    app.include_router(graph_chat.router)
    app.state.graph_runtime = graph_runtime
    with TestClient(app) as client:
        response = client.post("/api/graph-chat", json={
            "conversation_id": cid, "user_id": "u1", "message": "继续",
        })
    if kind is not None:
        assert response.status_code == 409
        assert response.json() == {"detail": detail}
        started.assert_not_called()
    else:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.text == "data: [DONE]\n\n"
        started.assert_called_once_with("u1", cid, graph_runtime)
    lookup.assert_not_awaited()
