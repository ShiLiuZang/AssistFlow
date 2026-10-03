"""/api/actions：待处理操作查询、工单确认恢复、订单选择（使用真实对话图 + 内存检查点）。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage

from app.api import actions
from app.graph import turns
from app.main import app
from app.schemas.actions import ResumeTicketRequest, SelectOrderRequest
from tests.api.conftest import conversation, sse_frames
from tests.graph.conftest import ORDER, make_services, runtime_for, scripted_agent, tool_call

TICKET_CALL = tool_call("c1", "create_ticket", {"reason": "坏了"})


@pytest.fixture
def action_repo(repo, monkeypatch):
    repo.set("get_conversation", return_value=conversation(7))
    repo.set("get_ticket_decision", return_value=None)
    repo.set("get_pending_ticket_call", return_value=None)
    repo.set("decide_ticket", return_value={"confirmed": True, "ticket_no": "T-1"})
    repo.set("list_messages", return_value=[SimpleNamespace(tool_calls=[TICKET_CALL])])
    repo.set("persist_graph_messages")
    repo.set("insert_trace_span")
    repo.set("insert_tool_audit")
    repo.set("save_turn")
    repo.set("capture_low_confidence")
    repo.schedule = Mock()
    monkeypatch.setattr(turns, "schedule_persisted_summary", repo.schedule)
    return repo


async def ticket_runtime():
    agent = scripted_agent(AIMessage(content="", tool_calls=[TICKET_CALL]), AIMessage(content="模型总结"))
    runtime = runtime_for(make_services(route="business", agent=agent))
    await runtime.run_turn("我要报修", "u1", "7")
    return runtime


async def order_runtime():
    runtime = runtime_for(make_services(
        route="refund",
        list_orders=AsyncMock(return_value=[ORDER, {**ORDER, "order_id": "ORD-2"}]),
        get_order=AsyncMock(return_value=ORDER),
    ))
    first = await runtime.run_turn("我要退款", "u1", "7")
    return runtime, first["request_id"]


class TestPending:
    def test_404_for_unknown_conversation(self, client, action_repo):
        action_repo.get_conversation.return_value = None
        assert client.get("/api/actions/pending", params={"conversation_id": 7, "user_id": "u1"}).status_code == 404

    def test_none_without_anything_pending(self, client, action_repo):
        assert client.get("/api/actions/pending", params={"conversation_id": 7, "user_id": "u1"}).json() is None

    def test_legacy_pending_ticket_from_database(self, client, action_repo):
        action_repo.get_pending_ticket_call.return_value = {"id": "c9", "args": {"reason": "x"}}
        action_repo.get_ticket_decision.return_value = {"confirmed": False}
        assert client.get("/api/actions/pending", params={"conversation_id": 7, "user_id": "u1"}).json() == {
            "kind": "confirm_ticket", "conversation_id": 7, "tool_call_id": "c9",
            "preview": {"reason": "x"}, "confirmed": False,
        }

    async def test_graph_ticket_interrupt(self, client, action_repo):
        app.state.graph_runtime = await ticket_runtime()
        assert client.get("/api/actions/pending", params={"conversation_id": 7, "user_id": "u1"}).json() == {
            "kind": "confirm_ticket", "tool_call_id": "c1", "preview": {"reason": "坏了"},
            "conversation_id": 7, "confirmed": None,
        }

    async def test_graph_order_interrupt(self, client, action_repo):
        app.state.graph_runtime, request_id = await order_runtime()
        body = client.get("/api/actions/pending", params={"conversation_id": 7, "user_id": "u1"}).json()
        assert body["kind"] == "select_order"
        assert body["request_id"] == request_id
        assert body["conversation_id"] == 7
        action_repo.get_ticket_decision.assert_not_awaited()


class TestResumeEndpoint:
    BODY = {"conversation_id": 7, "user_id": "u1", "confirmed": True}

    def test_404(self, client, action_repo):
        action_repo.get_conversation.return_value = None
        assert client.post("/api/actions/resume", json=self.BODY).status_code == 404

    def test_409_without_pending_ticket(self, client, action_repo):
        assert client.post("/api/actions/resume", json=self.BODY).status_code == 409

    def test_409_when_call_not_in_history(self, client, action_repo):
        assert client.post("/api/actions/resume", json={**self.BODY, "tool_call_id": "zz"}).status_code == 409

    async def test_graph_requires_tool_call_id(self, client, action_repo):
        app.state.graph_runtime = await ticket_runtime()
        assert client.post("/api/actions/resume", json=self.BODY).status_code == 409

    @pytest.mark.parametrize("body", [{"confirmed": "yes"}, {"extra": 1}])
    def test_422(self, client, action_repo, body):
        assert client.post("/api/actions/resume", json={**self.BODY, **body}).status_code == 422

    def test_legacy_confirm(self, client, action_repo):
        action_repo.get_pending_ticket_call.return_value = {"id": "c1", "args": {}}

        frames = sse_frames(client.post("/api/actions/resume", json=self.BODY).text)

        assert frames == [
            (None, {"delta": "工单已创建，工单号：T-1"}),
            (None, {"event": "done", "conversation_id": 7}),
            (None, "[DONE]"),
        ]
        assert action_repo.decide_ticket.await_args.kwargs == {"graph": False}
        action_repo.insert_tool_audit.assert_awaited_once()
        action_repo.persist_graph_messages.assert_not_awaited()
        action_repo.schedule.assert_not_called()

    @pytest.mark.parametrize("confirmed", [True, False])
    async def test_graph_confirm_resumes_graph(self, client, action_repo, confirmed):
        runtime = await ticket_runtime()
        app.state.graph_runtime = runtime
        action_repo.decide_ticket.return_value = {"confirmed": confirmed, "ticket_no": "T-1"}

        response = client.post("/api/actions/resume", json={**self.BODY, "confirmed": confirmed, "tool_call_id": "c1"})

        frames = sse_frames(response.text)
        assert frames[-2] == (None, {"event": "done", "conversation_id": 7})
        assert action_repo.decide_ticket.await_args.args == (7, "u1", "c1", confirmed)
        assert action_repo.decide_ticket.await_args.kwargs == {"graph": True}
        action_repo.persist_graph_messages.assert_awaited_once()
        action_repo.schedule.assert_called_once()
        state = await runtime.graph.aget_state({"configurable": {"thread_id": "u1:7"}})
        assert not state.next

    async def test_decision_failure_yields_error(self, client, action_repo):
        app.state.graph_runtime = await ticket_runtime()
        action_repo.decide_ticket.side_effect = RuntimeError("db down")

        frames = sse_frames(client.post("/api/actions/resume", json={**self.BODY, "tool_call_id": "c1"}).text)

        assert frames[0][0] == "error"
        assert frames[-1] == (None, "[DONE]")
        action_repo.schedule.assert_not_called()


class TestStreamTicketDecision:
    REQUEST = ResumeTicketRequest(conversation_id=7, user_id="u1", confirmed=True, tool_call_id="c2")

    async def collect(self, request, call, runtime):
        return sse_frames("".join([c async for c in actions.stream_ticket_decision(request, call, runtime)]))

    async def test_mismatched_interrupt_rejected(self, action_repo):
        runtime = await ticket_runtime()
        frames = await self.collect(self.REQUEST, tool_call("c2", "create_ticket", {}), runtime)
        assert frames[0][0] == "error"
        action_repo.decide_ticket.assert_not_awaited()

    async def test_saved_decision_is_idempotent(self, action_repo):
        runtime = await ticket_runtime()
        action_repo.get_ticket_decision.return_value = {"confirmed": True}

        frames = await self.collect(self.REQUEST, tool_call("c2", "create_ticket", {}), runtime)

        assert frames[0][0] is None
        assert frames[0][1]["event"] == "interrupt"
        assert frames[0][1]["tool_call_id"] == "c1"
        action_repo.decide_ticket.assert_awaited_once()

    async def test_graph_without_interrupt_or_decision(self, action_repo):
        runtime = runtime_for(make_services(route="chat"))
        await runtime.run_turn("你好", "u1", "7")
        frames = await self.collect(self.REQUEST, TICKET_CALL, runtime)
        assert frames[0][0] == "error"

    async def test_bad_audit_does_not_break_decision(self, action_repo):
        action_repo.decide_ticket.return_value = {"confirmed": "yes", "ticket_no": "T-1"}
        frames = await self.collect(self.REQUEST, TICKET_CALL, None)
        assert frames[-2] == (None, {"event": "done", "conversation_id": 7})
        action_repo.insert_tool_audit.assert_not_awaited()


class TestSelectOrder:
    def body(self, request_id, **extra):
        return {"conversation_id": 7, "user_id": "u1", "request_id": request_id, **extra}

    def test_404_and_503(self, client, action_repo):
        assert client.post("/api/actions/select-order", json=self.body("r", order_id="ORD-1")).status_code == 503
        action_repo.get_conversation.return_value = None
        assert client.post("/api/actions/select-order", json=self.body("r", order_id="ORD-1")).status_code == 404

    @pytest.mark.parametrize(
        "extra",
        [{}, {"order_id": "ORD-1", "cancelled": True}, {"cancelled": "true"}, {"order_id": ""}, {"kind": "other"}],
    )
    def test_422(self, client, action_repo, extra):
        assert client.post("/api/actions/select-order", json=self.body("r", **extra)).status_code == 422

    async def test_select_resumes_and_answers(self, client, action_repo):
        app.state.graph_runtime, request_id = await order_runtime()

        frames = sse_frames(client.post("/api/actions/select-order", json=self.body(request_id, order_id="ORD-1")).text)

        events = [data.get("event") for _, data in frames if isinstance(data, dict)]
        assert "done" in events
        assert "end" not in events
        assert frames[-1] == (None, "[DONE]")
        action_repo.persist_graph_messages.assert_awaited_once()
        action_repo.schedule.assert_called_once()

    async def test_cancel(self, client, action_repo):
        app.state.graph_runtime, request_id = await order_runtime()
        frames = sse_frames(client.post("/api/actions/select-order", json=self.body(request_id, cancelled=True)).text)
        assert any(isinstance(d, dict) and d.get("event") == "done" for _, d in frames)

    async def test_stale_request_id_yields_error(self, client, action_repo):
        app.state.graph_runtime, _ = await order_runtime()
        frames = sse_frames(client.post("/api/actions/select-order", json=self.body("stale", order_id="ORD-1")).text)
        assert [event for event, _ in frames if event] == ["error"]
        action_repo.schedule.assert_not_called()

    async def test_persist_failure(self, action_repo):
        runtime, request_id = await order_runtime()
        action_repo.persist_graph_messages.side_effect = RuntimeError()
        request = SelectOrderRequest(conversation_id=7, user_id="u1", request_id=request_id, order_id="ORD-1")

        frames = sse_frames("".join([c async for c in actions.stream_order_selection(request, runtime)]))

        assert frames == [
            ("error", {"message": "订单选择或消息保存失败，请检查当前待处理状态"}),
            (None, "[DONE]"),
        ]
