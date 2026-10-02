"""app.api.graph_chat：消息一致性校验、流式编排与 HTTP 接口（数据库与图运行时均为替身）。"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.api import graph_chat
from app.schemas.chat import ChatRequest


def row(row_id, role, content="", tool_calls=None, tool_call_id=None):
    return SimpleNamespace(
        id=row_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        turn_message_id=None,
    )


CALL = {"id": "c1", "name": "get_order", "args": {"order_id": "ORD-1"}, "type": "tool_call"}


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
        HumanMessage(content="图里多出来的新消息"),
    ]

    def test_counts_up_to_cursor(self):
        assert graph_chat.count_covered_messages(self.RECORDS, self.MESSAGES, 3) == 3
        assert graph_chat.count_covered_messages(self.RECORDS, self.MESSAGES, 0) == 0
        assert graph_chat.count_covered_messages(self.RECORDS, self.MESSAGES, 5) == 4

    def test_db_longer_than_graph(self):
        with pytest.raises(ValueError, match="更长|长"):
            graph_chat.count_covered_messages(self.RECORDS, self.MESSAGES[:2], 0)

    @pytest.mark.parametrize(
        "index,replacement",
        [
            (0, AIMessage(content="查订单")),  # 类型不同
            (0, HumanMessage(content="别的")),  # 内容不同
            (1, AIMessage(content="", tool_calls=[])),  # 工具调用不同
            (2, ToolMessage(content="{}", tool_call_id="c2")),  # tool_call_id 不同
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


def test_thread_config():
    assert graph_chat._thread_config("u1", 7) == {"configurable": {"thread_id": "u1:7"}}


class FakeGraph:
    def __init__(self, values=None):
        self.values = values or {}
        self.updates = []

    async def aget_state(self, config):
        return SimpleNamespace(values=self.values)

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
    {"delta": "你好"},
    {"event": "done", "request_id": "r1", "message_id": "m1"},
    {"event": "end"},
]


@pytest.fixture
def repo(monkeypatch):
    fake = SimpleNamespace(
        get_conversation=AsyncMock(
            return_value=SimpleNamespace(id=7, summary_text="", summary_upto=0),
        ),
        list_messages=AsyncMock(return_value=[]),
        persist_graph_messages=AsyncMock(),
        create_conversation=AsyncMock(return_value=42),
        get_pending_ticket_call=AsyncMock(return_value=None),
    )
    for name, value in vars(fake).items():
        monkeypatch.setattr(graph_chat.repository, name, value)
    schedule = Mock()
    monkeypatch.setattr(graph_chat, "schedule_persisted_summary", schedule)
    fake.schedule_summary = schedule
    return fake


async def collect(stream):
    return [chunk async for chunk in stream]


def data_frames(chunks):
    return [
        json.loads(chunk.removeprefix("data: "))
        for chunk in chunks
        if chunk.startswith("data: {")
    ]


class TestStreamGraphChat:
    REQUEST = ChatRequest(user_id="u1", message="你好", conversation_id=7)

    async def test_restores_history_and_schedules_summary(self, repo):
        repo.get_conversation.return_value = SimpleNamespace(id=7, summary_text="旧摘要", summary_upto=1)
        repo.list_messages.return_value = [row(1, "user", "上一轮"), row(2, "assistant", "回答")]
        runtime = FakeRuntime(DONE_EVENTS)

        chunks = await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, runtime))

        frames = data_frames(chunks)
        assert frames[0] == {"event": "conversation", "conversation_id": 7}
        assert {"event": "done", "request_id": "r1", "message_id": "m1", "conversation_id": 7} in frames
        assert chunks[-1] == "data: [DONE]\n\n"
        assert chunks.count("data: [DONE]\n\n") == 1  # end 事件不重复输出

        # 图状态为空时用数据库历史初始化
        (_, values, as_node), = runtime.graph.updates
        assert [m.content for m in values["messages"]] == ["上一轮", "回答"]
        assert as_node == "finish"

        query, user_id, conversation_id, kwargs = runtime.calls[0]
        assert (query, user_id, conversation_id) == ("你好", "u1", "7")
        assert kwargs == {"summary_text": "旧摘要", "summary_upto": 1, "covered_count": 1}

        repo.persist_graph_messages.assert_awaited_once()
        repo.schedule_summary.assert_called_once()

    async def test_existing_graph_state_is_source_of_truth(self, repo):
        runtime = FakeRuntime(DONE_EVENTS, values={"messages": [HumanMessage(content="x")]})

        await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, runtime))

        assert runtime.graph.updates == []

    async def test_interrupt_skips_summary(self, repo):
        events = [
            {"event": "interrupt", "preview": {"kind": "select_order", "orders": []}},
            {"event": "end"},
        ]

        chunks = await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, FakeRuntime(events)))

        assert any(f.get("event") == "interrupt" and f["kind"] == "select_order" for f in data_frames(chunks))
        repo.schedule_summary.assert_not_called()
        repo.persist_graph_messages.assert_awaited_once()

    async def test_missing_conversation_yields_error(self, repo):
        repo.get_conversation.return_value = None

        chunks = await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, FakeRuntime(DONE_EVENTS)))

        assert chunks[-2].startswith("event: error")
        assert chunks[-1] == "data: [DONE]\n\n"
        repo.persist_graph_messages.assert_not_awaited()

    async def test_inconsistent_history_yields_error(self, repo):
        repo.list_messages.return_value = [row(1, "user", "数据库里的")]
        runtime = FakeRuntime(DONE_EVENTS, values={"messages": [HumanMessage(content="图里的")]})

        chunks = await collect(graph_chat.stream_graph_chat(self.REQUEST, 7, runtime))

        assert chunks[-2].startswith("event: error")
        assert runtime.calls == []


class TestGraphChatEndpoint:
    @staticmethod
    def client(runtime):
        app = FastAPI()
        app.include_router(graph_chat.router)
        if runtime is not None:
            app.state.graph_runtime = runtime
        return TestClient(app)

    def test_503_without_runtime(self, repo):
        response = self.client(None).post("/api/graph-chat", json={"user_id": "u1", "message": "hi"})
        assert response.status_code == 503

    def test_422_on_empty_message(self, repo):
        response = self.client(FakeRuntime(DONE_EVENTS)).post(
            "/api/graph-chat", json={"user_id": "u1", "message": ""},
        )
        assert response.status_code == 422

    def test_creates_conversation(self, repo):
        response = self.client(FakeRuntime(DONE_EVENTS)).post(
            "/api/graph-chat", json={"user_id": "u1", "message": "hi"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        repo.create_conversation.assert_awaited_once_with("u1")
        assert '"conversation_id": 42' in response.text
        assert "event: error" not in response.text

    def test_404_for_unknown_conversation(self, repo):
        repo.get_conversation.return_value = None
        response = self.client(FakeRuntime(DONE_EVENTS)).post(
            "/api/graph-chat", json={"user_id": "u1", "message": "hi", "conversation_id": 9},
        )
        assert response.status_code == 404

    def test_409_when_ticket_pending(self, repo):
        repo.get_pending_ticket_call.return_value = {"id": "t1"}
        response = self.client(FakeRuntime(DONE_EVENTS)).post(
            "/api/graph-chat", json={"user_id": "u1", "message": "hi", "conversation_id": 7},
        )
        assert response.status_code == 409
