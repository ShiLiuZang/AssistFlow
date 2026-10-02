"""聊天接口：/api/graph-chat 与会话历史（图运行时、模型、数据库均为替身）。"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.api import graph_chat, sse
from app.main import app
from app.schemas.chat import ChatRequest
from tests.api.conftest import conversation, sse_frames


def row(row_id, role, content="", tool_calls=None, tool_call_id=None, turn_message_id=None):
    return SimpleNamespace(id=row_id, role=role, content=content, tool_calls=tool_calls,
                           tool_call_id=tool_call_id, turn_message_id=turn_message_id)


CALL = {"id": "c1", "name": "query_order", "args": {"order_id": "ORD-1"}, "type": "tool_call"}


class TestSseHelpers:
    def test_make_sse(self):
        assert sse.make_sse({"delta": "你好"}) == 'data: {"delta": "你好"}\n\n'

    @pytest.mark.parametrize(
        "event,expected",
        [
            ({"event": "end"}, "data: [DONE]\n\n"),
            ({"event": "error", "message": "x"}, 'event: error\ndata: {"message":"图执行失败，请重试"}\n\n'),
            ({"event": "citations", "citations": [1]}, 'data: {"event": "citations", "items": [1]}\n\n'),
            ({"event": "done", "request_id": "r"}, 'data: {"event": "done", "request_id": "r", "conversation_id": 7}\n\n'),
            ({"event": "interrupt", "preview": {"kind": "k"}}, 'data: {"event": "interrupt", "conversation_id": 7, "kind": "k"}\n\n'),
            ({"delta": "x"}, 'data: {"delta": "x"}\n\n'),
        ],
    )
    def test_graph_event_to_sse(self, event, expected):
        assert sse.graph_event_to_sse(event, 7) == expected

    @pytest.mark.parametrize(
        "content,status",
        [('{"found": true}', "success"), ('{"error": "x"}', "error"), ("not json", "error"), ("[1]", "error")],
    )
    def test_restored_tool_status(self, content, status):
        assert sse.restored_tool_status(content) == status

    def test_restore_messages(self):
        messages = sse.restore_messages([
            row(1, "user", "查订单"),
            row(2, "assistant", None, tool_calls=[CALL], turn_message_id="m1"),
            row(3, "tool", '{"found": true}', tool_call_id="c1"),
            row(4, "system", "忽略"),
        ])
        assert [type(m) for m in messages] == [HumanMessage, AIMessage, ToolMessage]
        assert messages[1].id == "m1"
        assert messages[1].tool_calls[0]["id"] == "c1"
        assert (messages[2].tool_call_id, messages[2].status) == ("c1", "success")


class TestCountCoveredMessages:
    RECORDS = [
        row(1, "user", "查订单"),
        row(2, "assistant", "", tool_calls=[CALL]),
        row(3, "tool", "{}", tool_call_id="c1"),
        row(4, "system", "忽略"),
        row(5, "assistant", "已发货"),
    ]
    MESSAGES = [
        HumanMessage(content="查订单"),
        AIMessage(content="", tool_calls=[CALL]),
        ToolMessage(content="{}", tool_call_id="c1"),
        AIMessage(content="已发货"),
        HumanMessage(content="图里多出的新消息"),
    ]

    @pytest.mark.parametrize("cursor,count", [(0, 0), (3, 3), (5, 4)])
    def test_counts_up_to_cursor(self, cursor, count):
        assert graph_chat.count_covered_messages(self.RECORDS, self.MESSAGES, cursor) == count

    def test_db_longer_than_graph(self):
        with pytest.raises(ValueError, match="比图历史长"):
            graph_chat.count_covered_messages(self.RECORDS, self.MESSAGES[:2], 0)

    @pytest.mark.parametrize(
        "index,replacement",
        [
            (0, AIMessage(content="查订单")),
            (0, HumanMessage(content="别的")),
            (1, AIMessage(content="", tool_calls=[])),
            (2, ToolMessage(content="{}", tool_call_id="c2")),
        ],
    )
    def test_detects_mismatch(self, index, replacement):
        messages = list(self.MESSAGES)
        messages[index] = replacement
        with pytest.raises(ValueError, match="不一致"):
            graph_chat.count_covered_messages(self.RECORDS, messages, 0)

    def test_cursor_must_point_to_model_message(self):
        with pytest.raises(ValueError, match="游标"):
            graph_chat.count_covered_messages(self.RECORDS, self.MESSAGES, 4)


class FakeGraph:
    def __init__(self, values=None, next_nodes=()):
        self.values = values or {}
        self.next = next_nodes
        self.updates = []

    async def aget_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next, tasks=[])

    async def aupdate_state(self, config, values, as_node=None):
        self.updates.append((config, values, as_node))


class FakeRuntime:
    def __init__(self, events, values=None):
        self.graph = FakeGraph(values)
        self.events = events
        self.calls = []

    async def stream_turn(self, query, user_id, conversation_id, **kwargs):
        self.calls.append((query, user_id, conversation_id, kwargs))
        for event in self.events:
            yield event


DONE_EVENTS = [
    {"event": "node", "name": "classify"},
    {"event": "citations", "citations": [{"n": 1}]},
    {"delta": "你好"},
    {"event": "done", "request_id": "r1", "message_id": "m1"},
    {"event": "end"},
]


@pytest.fixture
def graph_repo(repo, monkeypatch):
    repo.set("get_conversation", return_value=conversation())
    repo.set("list_messages", return_value=[])
    repo.set("persist_graph_messages")
    repo.set("create_conversation", return_value=42)
    repo.set("get_pending_ticket_call", return_value=None)
    repo.schedule = Mock()
    monkeypatch.setattr(graph_chat, "schedule_persisted_summary", repo.schedule)
    return repo


async def collect(stream):
    return [chunk async for chunk in stream]


class TestStreamGraphChat:
    REQUEST = ChatRequest(user_id="u1", message="你好", conversation_id=7)

    async def test_turn_timeout_yields_friendly_error(self, graph_repo, monkeypatch):
        import asyncio

        from app.config import settings

        class SlowRuntime(FakeRuntime):
            async def stream_turn(self, *args, **kwargs):
                await asyncio.sleep(1)
                yield {"event": "end"}

        monkeypatch.setattr(settings, "chat_turn_timeout_seconds", 0.01)
        frames = sse_frames("".join(await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, SlowRuntime([])))))

        assert ("error", {"message": "当前咨询较多，请稍后重试或转人工"}) in frames
        assert frames[-1] == (None, "[DONE]")
        graph_repo.persist_graph_messages.assert_not_awaited()

    async def test_restores_history_streams_and_schedules_summary(self, graph_repo):
        graph_repo.get_conversation.return_value = conversation(summary_text="旧摘要", summary_upto=1)
        graph_repo.list_messages.return_value = [row(1, "user", "上一轮"), row(2, "assistant", "回答")]
        runtime = FakeRuntime(DONE_EVENTS)

        frames = sse_frames("".join(await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, runtime))))

        assert frames[0] == (None, {"event": "conversation", "conversation_id": 7})
        assert (None, {"event": "citations", "items": [{"n": 1}]}) in frames
        assert (None, {"delta": "你好"}) in frames
        assert frames[-1] == (None, "[DONE]")
        assert [f for f in frames if f[1] == "[DONE]"] == [(None, "[DONE]")]

        (config, values, as_node), = runtime.graph.updates
        assert config == {"configurable": {"thread_id": "u1:7"}}
        assert [m.content for m in values["messages"]] == ["上一轮", "回答"]
        assert as_node == "finish"
        _, _, conversation_id, kwargs = runtime.calls[0]
        assert conversation_id == "7"
        assert kwargs == {"summary_text": "旧摘要", "summary_upto": 1, "covered_count": 1}
        graph_repo.persist_graph_messages.assert_awaited_once()
        graph_repo.schedule.assert_called_once()

    async def test_existing_graph_state_is_source_of_truth(self, graph_repo):
        runtime = FakeRuntime(DONE_EVENTS, values={"messages": [HumanMessage(content="x")]})
        await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, runtime))
        assert runtime.graph.updates == []

    @pytest.mark.parametrize(
        "events",
        [
            [{"event": "interrupt", "preview": {"kind": "select_order"}}, {"event": "end"}],
            [{"event": "error", "message": "x"}, {"event": "end"}],
        ],
    )
    async def test_interrupt_or_error_skips_summary(self, graph_repo, events):
        await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, FakeRuntime(events)))
        graph_repo.schedule.assert_not_called()
        graph_repo.persist_graph_messages.assert_awaited_once()

    async def test_missing_conversation_yields_error(self, graph_repo):
        graph_repo.get_conversation.return_value = None
        chunks = await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, FakeRuntime(DONE_EVENTS)))
        assert chunks[-2].startswith("event: error")
        assert chunks[-1] == "data: [DONE]\n\n"

    async def test_inconsistent_history_yields_error(self, graph_repo):
        graph_repo.list_messages.return_value = [row(1, "user", "数据库里的")]
        runtime = FakeRuntime(DONE_EVENTS, values={"messages": [HumanMessage(content="图里的")]})
        chunks = await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, runtime))
        assert chunks[-2].startswith("event: error")
        assert runtime.calls == []


class TestHandoffRouting:
    REQUEST = ChatRequest(user_id="u1", message="在吗", conversation_id=7)

    async def test_message_goes_to_agent_while_handoff_open(self, graph_repo, monkeypatch):
        from app.core import handoff

        async def routed(conversation_id, user_id, text):
            return {"handoff": {"status": "active"}, "message": {"role": "customer", "content": text}}

        monkeypatch.setattr(handoff, "customer_message", routed)
        runtime = FakeRuntime(DONE_EVENTS)
        frames = sse_frames("".join(await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, runtime))))

        assert runtime.calls == []
        assert frames[1][1]["event"] == "handoff" and frames[1][1]["handoff"] == {"status": "active"}
        assert frames[2][1] == {"event": "done", "conversation_id": 7, "message_id": None, "handoff": True}
        assert frames[-1] == (None, "[DONE]")
        graph_repo.persist_graph_messages.assert_not_awaited()

    async def test_turn_that_queues_reports_status(self, graph_repo, monkeypatch):
        from app.core import handoff

        async def status(conversation_id):
            return {"status": "queued", "position": 2}

        monkeypatch.setattr(handoff, "open_status", status)
        frames = sse_frames("".join(await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, FakeRuntime(DONE_EVENTS)))))
        assert (None, {"event": "handoff", "conversation_id": 7, "handoff": {"status": "queued", "position": 2}}) in frames
        assert any(f[1].get("event") == "done" for f in frames if isinstance(f[1], dict))

    async def test_status_lookup_failure_does_not_break_turn(self, graph_repo, monkeypatch):
        from app.core import handoff

        async def broken(conversation_id):
            raise RuntimeError("db")

        monkeypatch.setattr(handoff, "open_status", broken)
        frames = sse_frames("".join(await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, FakeRuntime(DONE_EVENTS)))))
        assert all(event != "error" for event, _ in frames)


class TestGraphChatEndpoint:
    def test_503_without_runtime(self, client, graph_repo):
        assert client.post("/api/graph-chat", json={"user_id": "u1", "message": "hi"}).status_code == 503

    @pytest.mark.parametrize("body", [{"message": ""}, {"message": "长" * 2001}, {"conversation_id": 1}])
    def test_422_on_invalid_body(self, client, graph_repo, body):
        app.state.graph_runtime = FakeRuntime(DONE_EVENTS)
        assert client.post("/api/graph-chat", json=body).status_code == 422

    def test_creates_conversation(self, client, graph_repo):
        app.state.graph_runtime = FakeRuntime(DONE_EVENTS)
        response = client.post("/api/graph-chat", json={"user_id": "u1", "message": "hi"})

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        graph_repo.create_conversation.assert_awaited_once_with("u1")
        frames = sse_frames(response.text)
        assert frames[0][1] == {"event": "conversation", "conversation_id": 42}
        assert all(event != "error" for event, _ in frames)

    def test_404_for_unknown_conversation(self, client, graph_repo):
        app.state.graph_runtime = FakeRuntime(DONE_EVENTS)
        graph_repo.get_conversation.return_value = None
        response = client.post("/api/graph-chat", json={"user_id": "u1", "message": "hi", "conversation_id": 9})
        assert response.status_code == 404

    def test_409_when_ticket_pending(self, client, graph_repo):
        app.state.graph_runtime = FakeRuntime(DONE_EVENTS)
        graph_repo.get_pending_ticket_call.return_value = {"id": "t1"}
        response = client.post("/api/graph-chat", json={"user_id": "u1", "message": "hi", "conversation_id": 7})
        assert response.status_code == 409



class TestConversations:
    def test_list(self, client, repo):
        from datetime import datetime

        repo.set("list_conversations", return_value=[SimpleNamespace(id=1, created_at=datetime(2026, 1, 2, 3, 4))])
        assert client.get("/api/conversations", params={"user_id": "u1"}).json() == [
            {"id": 1, "created_at": "2026-01-02T03:04:00"},
        ]

    def test_messages(self, client, repo):
        repo.set("get_conversation", return_value=conversation(1))
        repo.set("list_dialog_messages", return_value=[
            SimpleNamespace(role="user", content="hi", turn_message_id=None),
            SimpleNamespace(role="assistant", content="hello", turn_message_id="m1"),
        ])
        response = client.get("/api/conversations/1/messages", params={"user_id": "u1"})
        assert response.json()[1] == {"role": "assistant", "content": "hello", "message_id": "m1"}
        repo.get_conversation.assert_awaited_once_with(1, "u1")

    def test_messages_include_human_service(self, client, repo):
        repo.set("get_conversation", return_value=conversation(1))
        repo.set("list_dialog_messages", return_value=[
            SimpleNamespace(role="handoff_event", content="人工客服已接入", turn_message_id=None),
            SimpleNamespace(role="handoff_user", content="在吗", turn_message_id=None),
            SimpleNamespace(role="staff", content="在的", turn_message_id=None),
        ])
        roles = [m["role"] for m in client.get("/api/conversations/1/messages").json()]
        assert roles == ["system", "user", "staff"]
        repo.get_conversation.assert_awaited_once_with(1, "u1")

    def test_messages_of_other_user_404(self, client, repo):
        repo.set("get_conversation", return_value=None)
        assert client.get("/api/conversations/1/messages", params={"user_id": "u2"}).status_code == 404


class TestFeedback:
    BODY = {"user_id": "u1", "conversation_id": 1, "message_id": "m1", "rating": "down"}

    @pytest.fixture
    def feedback_repo(self, repo):
        repo.set("get_conversation", return_value=conversation(1))
        repo.set("submit_feedback", return_value=9)
        return repo

    def test_down_vote_enters_pool(self, client, feedback_repo):
        assert client.post("/api/feedback", json=self.BODY).json() == {
            "success": True, "message": "感谢您的反馈，我们会尽快改进", "pool_id": 9,
        }
        assert feedback_repo.submit_feedback.await_args.kwargs == {
            "owner": "u1", "conversation": "1", "message_id": "m1", "rating": "down",
        }

    def test_up_vote(self, client, feedback_repo):
        feedback_repo.submit_feedback.return_value = None
        assert client.post("/api/feedback", json={**self.BODY, "rating": "up"}).json()["pool_id"] is None

    @pytest.mark.parametrize(
        "setup,status",
        [
            (lambda r: None, 400),
            (lambda r: setattr(r.get_conversation, "return_value", None), 404),
            (lambda r: setattr(r.submit_feedback, "side_effect", PermissionError()), 403),
            (lambda r: setattr(r.submit_feedback, "side_effect", ValueError("重复反馈")), 400),
            (lambda r: setattr(r.submit_feedback, "side_effect", RuntimeError()), 500),
        ],
    )
    def test_errors(self, client, feedback_repo, setup, status):
        setup(feedback_repo)
        body = {**self.BODY, "rating": "meh"} if status == 400 and feedback_repo.submit_feedback.side_effect is None else self.BODY
        assert client.post("/api/feedback", json=body).status_code == status
