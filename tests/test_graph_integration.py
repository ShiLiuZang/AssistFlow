"""
测试主图的端到端流程回归
使用假服务和一次性SQLite，覆盖所有意图分支
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver

from app.core.intent import Intent, Prediction, ROUTES
from app.graph.build import build_graph
from app.graph.runtime import Runtime
from app.graph.adapters import make_tool_registry
from app.api import graph_chat
from app.api.sse import graph_event_to_sse
from app.core.evidence import REFUSAL
from app.core.llm import get_chat_model


def fake_services(intent=Intent.REFUND, route=None):
    """构造假服务对象，模拟各种意图的响应"""
    order = {"order_id": "ORD-1001", "user_id": "u1", "product_name": "杯子", "status": "已发货"}
    hit = {
        "id": 1,
        "question": "退货条件",
        "answer": "退货需要核对签收时间",
        "section_path": "退货",
        "rerank_score": 0.9,
    }
    return SimpleNamespace(
        max_steps=3,
        classify=AsyncMock(return_value=(Prediction(intent=intent, confidence=0.9), route or ROUTES[intent])),
        retrieve_detailed=AsyncMock(return_value={"candidates": [hit], "evidence": [hit]}),
        check_sufficient=AsyncMock(return_value={"useful": True}),
        rerank_policy=AsyncMock(return_value=[hit]),
        answer=AsyncMock(return_value={
            "answer": "请核对签收时间 [1]",
            "refused": False,
            "citations": [hit],
            "reason": None,
        }),
        agent=AsyncMock(return_value=AIMessage(content="订单信息")),
        registry=make_tool_registry(), list_orders=AsyncMock(return_value=[order]),
        get_order=AsyncMock(return_value=order), expand_policy=AsyncMock(return_value=[]),
    )


def runtime(s):
    """构造运行时对象"""
    return Runtime(build_graph(s, InMemorySaver()))


@pytest.mark.parametrize("intent", list(Intent))
def test_all_intents_take_expected_graph_branch(intent):
    """测试所有意图：每种意图都路由到预期的图分支"""
    async def run():
        s = fake_services(intent)
        result = await runtime(s).run_turn("ORD-1001 请处理", "u1", "routes")
        node = {"knowledge": "retrieve", "business": "agent", "refund": "fetch_order",
                "complaint": "complaint", "human": "human", "chat": "chat",
                "clarify": "clarify_intent"}[ROUTES[intent]]
        assert result["trace"][:3] == ["resolve_reference", "classify", node]
        assert result["intent_detail"] == intent.value
        assert result["messages"][-1].content == result["answer"]
        if ROUTES[intent] in {"human", "clarify", "chat", "complaint"}:
            s.retrieve_detailed.assert_not_awaited()
            s.agent.assert_not_awaited()
        s.classify.assert_awaited_once()
    asyncio.run(run())


def test_runtime_history_and_turn_share_normalized_thread():
    """整数和字符串 ID 共用历史及轮次状态，不同用户保持隔离。"""
    async def run():
        r = runtime(fake_services(Intent.CHAT))
        history = [HumanMessage(content="第一轮问题"), AIMessage(content="第一轮回答")]
        await r.seed_messages("u1", 7, history)
        seeded = await r.get_state("u1", "7")
        assert seeded.values["messages"] == history
        assert not seeded.next
        assert await r.pending_interrupt("u1", 7) is None

        result = await r.run_turn("第二轮问题", "u1", 7)
        snapshot = await r.get_state("u1", "7")
        assert result["conversation_id"] == "7"
        assert snapshot.values["messages"][:2] == history
        assert snapshot.values["messages"] == result["messages"]
        assert (await r.get_state("u2", 7)).values == {}
        assert r.config("u1", 7) == r.config("u1", "7") == {
            "configurable": {"thread_id": "u1:7"}, "recursion_limit": 64,
        }
    asyncio.run(run())


def test_runtime_continue_turn_retries_failed_node_with_span():
    """继续执行失败节点，沿用会话历史并导出 graph_turn span。"""
    async def run():
        s = fake_services(Intent.ORDER)
        s.agent = AsyncMock(side_effect=[RuntimeError("test failure"), AIMessage(content="重试完成")])
        sink = AsyncMock()
        r = Runtime(build_graph(s, InMemorySaver()), trace_sink=sink)
        with pytest.raises(RuntimeError, match="test failure"):
            await r.run_turn("订单状态", "u1", 7)
        failed = await r.get_state("u1", "7")
        assert failed.next == ("agent",)

        result = await r.continue_turn("u1", "7")
        latest = await r.get_state("u1", 7)
        assert not latest.next
        assert result["answer"] == "重试完成"
        assert result["conversation_id"] == "7"
        assert [message.type for message in result["messages"]] == ["human", "ai"]
        assert s.classify.await_count == 1
        assert s.agent.await_count == 2
        spans = [call.args[0] for call in sink.await_args_list if call.args[0]["name"] == "graph_turn"]
        assert [record["status"] for record in spans] == ["error", "ok"]
    asyncio.run(run())


class StreamingModel(BaseChatModel):
    """离线模型，首块后可暂停；强制验证 LangGraph 使用真实模型流。"""
    chunks: list[AIMessageChunk]
    release: asyncio.Event | None = None
    finished: asyncio.Event | None = None

    @property
    def _llm_type(self):
        return "test-stream"

    def _generate(self, *args, **kwargs):
        raise AssertionError("应通过 messages 模式调用模型流")

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        for index, chunk in enumerate(self.chunks):
            yield ChatGenerationChunk(message=chunk)
            if index == 0 and self.release is not None:
                await self.release.wait()
        if self.finished is not None:
            self.finished.set()


def test_agent_tokens_arrive_before_graph_and_persistence_complete(monkeypatch):
    async def run():
        release, finished = asyncio.Event(), asyncio.Event()
        usage = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}
        model = StreamingModel(chunks=[
            AIMessageChunk(content="你", id="reply"),
            AIMessageChunk(content="好", id="reply"),
            AIMessageChunk(content="", id="reply", usage_metadata=usage),
        ], release=release, finished=finished)
        s = fake_services(Intent.ORDER)
        sink = AsyncMock()
        s.trace_sink = sink

        async def agent(messages, **kwargs):
            return await model.ainvoke(messages)

        s.agent = agent
        r = Runtime(build_graph(s, InMemorySaver()), trace_sink=sink)
        saved, scheduled = AsyncMock(), Mock()
        monkeypatch.setattr(graph_chat, "_persist_graph_messages", saved)
        monkeypatch.setattr(graph_chat, "schedule_graph_summary", scheduled)
        stream = graph_chat.stream_graph_events(r, "u1", 7, r.stream_turn("订单状态", "u1", 7))
        frames = []
        while True:
            frame = await asyncio.wait_for(anext(stream), 2)
            frames.append(frame)
            if frame == graph_event_to_sse({"delta": "你"}, 7):
                break
        assert not finished.is_set()
        saved.assert_not_awaited()
        assert (await r.get_state("u1", 7)).next == ("agent",)
        release.set()
        frames.extend([frame async for frame in stream])
        from tests.test_graph_flow import events
        emitted = events(frames)
        assert [event["delta"] for event in emitted if "delta" in event] == ["你", "好"]
        snapshot = await r.get_state("u1", 7)
        assert [event["name"] for event in emitted if event.get("event") == "node"] == snapshot.values["trace"]
        assert emitted[-1] == {"event": "done", "request_id": snapshot.values["request_id"],
                               "message_id": None, "conversation_id": 7}
        assert not any(event.get("event") == "replace" for event in emitted)
        saved.assert_awaited_once_with(r, "u1", 7)
        scheduled.assert_called_once_with("u1", 7)
        agent_spans = [call.args[0] for call in sink.await_args_list if call.args[0]["name"] == "agent_model"]
        assert len(agent_spans) == 1
        assert agent_spans[0]["kind"] == "generation"
        # span 将 token_usage 展平为数据库追踪字段。
        assert {key: agent_spans[0][key] for key in usage} == usage
    asyncio.run(run())


def test_chat_model_requests_stream_usage():
    assert get_chat_model().stream_usage is True
    assert get_chat_model(streaming=True).stream_usage is True


@pytest.mark.parametrize("refused", [False, True])
def test_rag_candidate_tokens_are_hidden_until_grounding(refused):
    async def run():
        model = StreamingModel(chunks=[AIMessageChunk(content="未经"), AIMessageChunk(content="校验")])
        s = fake_services(Intent.PRODUCT)

        async def answer(*args, **kwargs):
            candidate = await model.ainvoke([HumanMessage(content="回答问题")])
            return {"answer": candidate.content, "refused": refused,
                    "reason": "unsupported_answer" if refused else None,
                    "citations": [] if refused else [{"id": 1}]}

        s.answer = answer
        r = runtime(s)
        emitted = [event async for event in r.stream_turn("产品说明", "u1", 7)]
        expected = REFUSAL if refused else "未经校验"
        assert [event for event in emitted if "delta" in event] == [{"delta": expected}]
        assert not any(event.get("event") == "replace" for event in emitted)
        snapshot = await r.get_state("u1", 7)
        names = [event["name"] for event in emitted if event.get("event") == "node"]
        assert names == snapshot.values["trace"] == ["resolve_reference", "classify", "retrieve", "answer", "finish"]
        if not refused:
            assert emitted[-4] == {"event": "citations", "citations": [{"id": 1}]}
        assert emitted[-3:] == [{"delta": expected}, {"event": "done", "request_id": snapshot.values["request_id"],
                                                    "message_id": None}, {"event": "end"}]
    asyncio.run(run())


@pytest.mark.parametrize("intent", [Intent.CHAT, Intent.HUMAN, Intent.OTHER, Intent.COMPLAINT])
def test_non_agent_routes_emit_one_final_delta(intent):
    async def run():
        r = runtime(fake_services(intent))
        emitted = [event async for event in r.stream_turn("请处理", "u1", 7)]
        snapshot = await r.get_state("u1", 7)
        assert [event for event in emitted if "delta" in event] == [{"delta": snapshot.values["answer"]}]
        assert [event["name"] for event in emitted if event.get("event") == "node"] == snapshot.values["trace"]
        assert emitted[-1] == {"event": "end"}
    asyncio.run(run())


@pytest.mark.parametrize("final_answer", ["最终答案", ""])
def test_stream_replaces_agent_text_rewritten_by_later_node(final_answer):
    async def astream(payload, **kwargs):
        assert kwargs["stream_mode"] == ["updates", "messages", "values"]
        yield "values", payload
        yield "messages", (AIMessageChunk(content="原始", id="reply"), {"langgraph_node": "agent"})
        yield "messages", (AIMessageChunk(content="回答", id="reply"), {"langgraph_node": "agent"})
        yield "updates", {"agent": {"answer": "原始回答"}}
        yield "updates", {"finish": {"answer": final_answer}}
        yield "values", {"answer": final_answer, "request_id": "r", "message_id": "m"}

    r = Runtime(SimpleNamespace(astream=astream, aget_state=AsyncMock(
        return_value=SimpleNamespace(values={}, tasks=[], next=()))))

    async def run():
        return [event async for event in r.stream_turn("问题", "u1", 7)]

    assert asyncio.run(run()) == [
        {"delta": "原始"}, {"delta": "回答"}, {"event": "node", "name": "agent"},
        {"event": "node", "name": "finish"}, {"event": "replace", "answer": final_answer},
        {"event": "done", "request_id": "r", "message_id": "m"}, {"event": "end"},
    ]


@pytest.mark.parametrize("query, resume, pending, next_nodes, error", [
    ("问题", None, "order", (), "请先确认或取消待处理操作"),
    ("", {}, None, (), "没有待恢复的操作"),
    ("新问题", None, None, ("agent",), "请先重试失败的问题"),
    ("新问题", {}, "order", (), "选择订单时不能同时发送新问题"),
    ("", True, "order", (), "选单恢复参数必须是字典"),
    ("", {}, "order", (), "恢复类型不匹配"),
    ("", {"kind": "select_order", "request_id": "old"}, "order", (), "选单请求已过期或不匹配"),
    ("", {"kind": "select_order", "request_id": "r", "cancelled": "yes"}, "order", (), "cancelled 必须为布尔值"),
    ("", {"kind": "select_order", "request_id": "r", "cancelled": True, "order_id": "o"}, "order", (), "取消不能同时选择订单"),
    ("", {"kind": "select_order", "request_id": "r"}, "order", (), "必须选择当前卡片中的订单"),
    ("", {"kind": "select_order", "request_id": "r", "order_id": "unknown"}, "order", (), "必须选择当前卡片中的订单"),
    ("", {"kind": "select_order"}, "ticket", (), "当前等待的不是订单选择"),
])
def test_stream_preserves_run_turn_validation_errors(query, resume, pending, next_nodes, error):
    card = {"kind": "select_order" if pending == "order" else "confirm_ticket",
            "request_id": "r", "orders": [{"order_id": "o"}]}
    tasks = [SimpleNamespace(interrupts=[SimpleNamespace(value=card)])] if pending else []
    graph = SimpleNamespace(ainvoke=AsyncMock(), astream=Mock(), aget_state=AsyncMock(
        return_value=SimpleNamespace(values={"query": "原问题"}, tasks=tasks, next=next_nodes)))
    r = Runtime(graph)

    async def run():
        with pytest.raises(ValueError, match=error):
            await r.run_turn(query, "u1", 7, resume=resume)
        return [event async for event in r.stream_turn(query, "u1", 7, resume=resume)]

    assert asyncio.run(run()) == [{"event": "error", "message": "图执行失败"}, {"event": "end"}]
    graph.ainvoke.assert_not_awaited()
    graph.astream.assert_not_called()


def test_stream_retries_failed_question_without_starting_new_turn():
    async def run():
        s = fake_services(Intent.ORDER)
        s.agent = AsyncMock(side_effect=[RuntimeError("test failure"), AIMessage(content="重试完成")])
        r = runtime(s)
        with pytest.raises(RuntimeError, match="test failure"):
            await r.run_turn("订单状态", "u1", 7)
        before = await r.get_state("u1", 7)
        emitted = [event async for event in r.stream_turn("订单状态", "u1", 7)]
        after = await r.get_state("u1", 7)
        assert after.values["request_id"] == before.values["request_id"]
        assert [event["name"] for event in emitted if event.get("event") == "node"] == ["agent", "finish"]
        assert [event for event in emitted if "delta" in event] == [{"delta": "重试完成"}]
        assert [message.type for message in after.values["messages"]] == ["human", "ai"]
        assert not after.next
        assert s.classify.await_count == 1
    asyncio.run(run())


def test_closing_runtime_stream_keeps_graph_running():
    async def run():
        release = asyncio.Event()
        model = StreamingModel(chunks=[AIMessageChunk(content="首块"), AIMessageChunk(content="尾块")], release=release)
        s = fake_services(Intent.ORDER)

        async def agent(messages, **kwargs):
            return await model.ainvoke(messages)

        s.agent = agent
        r = runtime(s)
        stream = r.stream_turn("问题", "u1", 7)
        while "delta" not in await asyncio.wait_for(anext(stream), 2):
            pass
        task, = r._stream_tasks
        await stream.aclose()
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, 2)
        snapshot = await r.get_state("u1", 7)
        assert not snapshot.next
        assert snapshot.values["answer"] == "首块尾块"
    asyncio.run(run())


@pytest.mark.parametrize("message_id", ["tool-reply", None])
def test_tool_call_and_non_agent_chunks_are_not_streamed(message_id):
    async def astream(payload, **kwargs):
        yield "values", payload
        yield "messages", (AIMessageChunk(content="内部分类"), {"langgraph_node": "classify"})
        yield "messages", (AIMessageChunk(content="工具说明", id=message_id, tool_call_chunks=[
            {"name": "query_order", "args": "{}", "id": "call", "index": 0},
        ]), {"langgraph_node": "agent"})
        yield "messages", (AIMessageChunk(content="同一工具消息的后续文字", id=message_id), {"langgraph_node": "agent"})
        yield "updates", {"agent": {"answer": ""}}
        yield "updates", {"tools": {}}
        yield "messages", (AIMessageChunk(content="最终回答", id="final" if message_id else None), {"langgraph_node": "agent"})
        yield "updates", {"agent": {"answer": "最终回答"}}
        yield "updates", {"finish": {}}
        yield "values", {"answer": "最终回答", "request_id": "r"}

    async def run():
        r = Runtime(SimpleNamespace(astream=astream, aget_state=AsyncMock(
            return_value=SimpleNamespace(values={}, tasks=[], next=()))))
        emitted = [event async for event in r.stream_turn("问题", "u1", 7)]
        assert [event for event in emitted if "delta" in event] == [{"delta": "最终回答"}]
        assert [event["name"] for event in emitted if event.get("event") == "node"] == ["agent", "tools", "agent", "finish"]
        assert not any(event.get("event") in {"replace", "error"} for event in emitted)
        assert emitted[-1] == {"event": "end"}
    asyncio.run(run())
