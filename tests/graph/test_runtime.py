"""app.graph.runtime / checkpoint：轮次校验、中断恢复、失败重试、流式事件与 SQLite 持久化。"""
from unittest.mock import AsyncMock

import pytest

from app.graph.checkpoint import persistent_runtime
from app.graph.runtime import FAILED_TURN_REPLY, close_failed_turn
from tests.graph.conftest import ANSWER, GOOD_HIT, ORDER, make_services, runtime_for


def order_services(**overrides):
    return make_services(route="refund", list_orders=AsyncMock(return_value=[ORDER]),
                         get_order=AsyncMock(return_value=ORDER), **overrides)


class TestRunTurnValidation:
    async def test_resume_without_pending(self, repo):
        with pytest.raises(ValueError, match="没有待恢复"):
            await runtime_for(make_services()).run_turn("", "u1", "c1", resume={"kind": "x"})

    async def test_new_question_blocked_while_interrupted(self, repo):
        runtime = runtime_for(order_services())
        await runtime.run_turn("我要退款", "u1", "c1")
        with pytest.raises(ValueError, match="待处理"):
            await runtime.run_turn("新问题", "u1", "c1")

    @pytest.mark.parametrize(
        "query,resume,message",
        [
            ("还有问题", {"kind": "select_order", "order_id": "ORD-1"}, "不能同时"),
            ("", "ORD-1", "字典"),
            ("", {"kind": "other"}, "类型不匹配"),
            ("", {"kind": "select_order", "request_id": "stale", "order_id": "ORD-1"}, "过期"),
            ("", {"kind": "select_order", "cancelled": "yes"}, "布尔"),
            ("", {"kind": "select_order", "cancelled": True, "order_id": "ORD-1"}, "取消不能"),
            ("", {"kind": "select_order", "order_id": "ORD-9"}, "卡片中的订单"),
            ("", {"kind": "select_order"}, "卡片中的订单"),
        ],
    )
    async def test_select_order_resume_validation(self, repo, query, resume, message):
        runtime = runtime_for(order_services())
        first = await runtime.run_turn("我要退款", "u1", "c1")
        if isinstance(resume, dict) and "request_id" not in resume:
            resume = {**resume, "request_id": first["request_id"]}

        with pytest.raises(ValueError, match=message):
            await runtime.run_turn(query, "u1", "c1", resume=resume)

    async def test_select_order_payload_rejected_for_other_interrupt(self, repo):
        from langchain_core.messages import AIMessage
        from tests.graph.conftest import scripted_agent, tool_call

        agent = scripted_agent(AIMessage(content="", tool_calls=[tool_call("c1", "create_ticket", {"reason": "x"})]))
        runtime = runtime_for(make_services(route="business", agent=agent))
        await runtime.run_turn("报修", "u1", "c1")

        with pytest.raises(ValueError, match="不是订单选择"):
            await runtime.run_turn("", "u1", "c1", resume={"kind": "select_order"})


class TestRetryAfterFailure:
    async def test_failed_turn_must_be_retried_with_same_question(self, repo):
        calls = {"n": 0}

        async def flaky(query):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("milvus down")
            return {"candidates": [GOOD_HIT], "evidence": [GOOD_HIT]}

        runtime = runtime_for(make_services(retrieve_detailed=flaky))
        with pytest.raises(RuntimeError):
            await runtime.run_turn("退货期限", "u1", "c1")

        result = await runtime.run_turn("退货期限", "u1", "c1")
        assert result["answer"] == ANSWER
        assert [m.type for m in result["messages"]] == ["human", "ai"]

    async def test_new_question_after_failure_closes_failed_turn(self, repo):
        calls = {"n": 0}

        async def flaky(query):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("milvus down")
            return {"candidates": [GOOD_HIT], "evidence": [GOOD_HIT]}

        runtime = runtime_for(make_services(retrieve_detailed=flaky))
        with pytest.raises(RuntimeError):
            await runtime.run_turn("退货期限", "u1", "c1")

        result = await runtime.run_turn("别的问题", "u1", "c1")
        assert result["answer"] == ANSWER
        assert [m.type for m in result["messages"]] == ["human", "ai", "human", "ai"]
        assert result["messages"][1].content == FAILED_TURN_REPLY
        assert result["messages"][2].content == "别的问题"

    async def test_new_question_after_timeout(self, repo):
        import asyncio

        async def slow(query):
            if query == "慢问题":
                await asyncio.sleep(5)
            return {"candidates": [GOOD_HIT], "evidence": [GOOD_HIT]}

        runtime = runtime_for(make_services(retrieve_detailed=slow))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(runtime.run_turn("慢问题", "u1", "c1"), timeout=0.2)

        result = await runtime.run_turn("退货期限", "u1", "c1")
        assert result["answer"] == ANSWER
        assert result["messages"][1].content == FAILED_TURN_REPLY

    async def test_empty_query_still_requires_retry(self, repo):
        async def boom(query):
            raise RuntimeError("milvus down")

        runtime = runtime_for(make_services(retrieve_detailed=boom))
        with pytest.raises(RuntimeError):
            await runtime.run_turn("退货期限", "u1", "c1")
        with pytest.raises(ValueError, match="重试失败"):
            await runtime.run_turn("", "u1", "c1")


class TestCloseFailedTurn:
    def test_dangling_tool_calls_get_error_results(self):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        messages = [
            HumanMessage(content="旧问题"), AIMessage(content="旧回答"),
            HumanMessage(content="查物流"),
            AIMessage(content="", tool_calls=[{"id": "a", "name": "x", "args": {}},
                                              {"id": "b", "name": "y", "args": {}}]),
            ToolMessage(content="{}", tool_call_id="a"),
        ]
        closing = close_failed_turn(messages)
        assert [(m.type, getattr(m, "tool_call_id", None)) for m in closing] == [("tool", "b"), ("ai", None)]
        assert closing[0].status == "error"
        assert closing[-1].content == FAILED_TURN_REPLY

    def test_no_tool_calls(self):
        from langchain_core.messages import HumanMessage

        closing = close_failed_turn([HumanMessage(content="问题")])
        assert [m.type for m in closing] == ["ai"]


class TestIsolationAndState:
    async def test_threads_isolated_per_user_and_conversation(self, repo):
        runtime = runtime_for(make_services())
        await runtime.run_turn("退货期限", "u1", "c1")
        await runtime.run_turn("退货期限", "u1", "c2")
        await runtime.run_turn("退货期限", "u2", "c1")
        await runtime.run_turn("还有呢", "u1", "c1")

        async def messages(thread):
            state = await runtime.graph.aget_state({"configurable": {"thread_id": thread}})
            return len(state.values["messages"])

        assert [await messages(t) for t in ("u1:c1", "u1:c2", "u2:c1")] == [4, 2, 2]

    async def test_each_turn_resets_per_turn_fields(self, repo):
        runtime = runtime_for(make_services())
        first = await runtime.run_turn("退货期限", "u1", "c1")
        second = await runtime.run_turn("退货期限", "u1", "c1")
        assert first["request_id"] != second["request_id"]
        assert second["trace"] == ["resolve_reference", "classify", "retrieve", "answer", "finish"]

    async def test_summary_fields_passed_through(self, repo):
        services = make_services()
        result = await runtime_for(services).run_turn(
            "退货期限", "u1", "c1", summary_text="旧摘要", summary_upto=3, covered_count=0,
        )
        assert (result["summary_text"], result["summary_upto"]) == ("旧摘要", 3)
        assert services.answer_calls[0]["summary_text"] == "旧摘要"

    async def test_covered_count_out_of_range(self, repo):
        with pytest.raises(ValueError, match="摘要覆盖"):
            await runtime_for(make_services()).run_turn("退货期限", "u1", "c1", covered_count=5)


class TestStreamTurn:
    async def test_answer_events(self, repo):
        events = [e async for e in runtime_for(make_services()).stream_turn("退货期限", "u1", "c1")]

        assert [e["name"] for e in events[:5]] == ["resolve_reference", "classify", "retrieve", "answer", "finish"]
        assert events[5]["event"] == "citations"
        assert events[6] == {"delta": ANSWER}
        assert events[7]["event"] == "done"
        assert events[7]["message_id"].startswith("msg_c1_")
        assert events[8] == {"event": "end"}

    async def test_no_citations_event_when_empty(self, repo):
        events = [e async for e in runtime_for(make_services(route="chat")).stream_turn("你好", "u1", "c1")]
        assert "citations" not in [e.get("event") for e in events]

    async def test_interrupt_event(self, repo):
        events = [e async for e in runtime_for(order_services()).stream_turn("我要退款", "u1", "c1")]
        assert events[-2]["event"] == "interrupt"
        assert events[-2]["preview"]["kind"] == "select_order"
        assert events[-1] == {"event": "end"}

    async def test_error_still_ends(self, repo):
        async def boom(query):
            raise RuntimeError("milvus down")

        events = [e async for e in runtime_for(make_services(retrieve_detailed=boom)).stream_turn("退货", "u1", "c1")]
        assert events == [{"event": "error", "message": "图执行失败"}, {"event": "end"}]

    async def test_trace_spans_exported(self, repo):
        spans = []

        async def sink(payload):
            spans.append(payload["name"])

        from app.graph.build import build_graph
        from app.graph.runtime import Runtime
        from langgraph.checkpoint.memory import InMemorySaver

        services = make_services()
        services.trace_sink = sink
        runtime = Runtime(build_graph(services, checkpointer=InMemorySaver()), trace_sink=sink)
        await runtime.run_turn("退货期限", "u1", "c1")

        assert {"graph_turn", "classify", "retrieve", "evidence_check", "answer"} <= set(spans)


async def test_persistent_runtime_survives_restart(tmp_path, repo):
    path = tmp_path / "nested" / "checkpoints.sqlite"

    async with persistent_runtime(order_services(), path) as runtime:
        first = await runtime.run_turn("我要退款", "u1", "c1")

    assert path.exists()

    async with persistent_runtime(order_services(), path) as runtime:
        result = await runtime.run_turn(
            "", "u1", "c1",
            resume={"kind": "select_order", "request_id": first["request_id"], "order_id": "ORD-1"},
        )

    assert result["trace"][-3:] == ["policy", "answer", "finish"]
