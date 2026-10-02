"""app.graph：路由函数与完整对话图编排（服务容器全部为替身，检查点用内存）。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph import nodes
from app.graph.build import build_graph
from app.graph.routing import confidence_gate, route_by_intent, should_continue
from app.graph.runtime import Runtime


class TestRouting:
    @pytest.mark.parametrize(
        "route",
        ["knowledge", "business", "refund", "complaint", "human", "chat", "clarify"],
    )
    def test_known_routes(self, route):
        assert route_by_intent({"route": route}) == route

    @pytest.mark.parametrize("state", [{}, {"route": "unknown"}, {"route": None}])
    def test_unknown_route_clarifies(self, state):
        assert route_by_intent(state) == "clarify"

    @pytest.mark.parametrize(
        "state,expected",
        [
            ({"evidence_allowed": True, "evidence": [{"id": 1}]}, "answer"),
            ({"evidence_allowed": True, "evidence": []}, "fallback"),
            ({"evidence_allowed": 1, "evidence": [{"id": 1}]}, "fallback"),
            ({}, "fallback"),
        ],
    )
    def test_confidence_gate(self, state, expected):
        assert confidence_gate(state) == expected

    def test_should_continue(self):
        call = {"id": "c1", "name": "get_order", "args": {}}
        assert should_continue({"messages": [AIMessage(content="", tool_calls=[call])]}) == "tools"
        assert should_continue({"messages": [AIMessage(content="完成")]}) == "finish"
        assert should_continue({}) == "finish"


GOOD_HIT = {
    "id": 1,
    "question": "退货期限",
    "answer": "签收后7天内可无理由退货。",
    "section_path": "售后/退货",
    "rerank_score": 0.9,
}


def prediction(intent="policy_qa", confidence=0.9):
    return SimpleNamespace(intent=SimpleNamespace(value=intent), confidence=confidence)


def make_services(route="knowledge", **overrides):
    async def classify(query, *, summary_text, recent_context):
        return prediction(), route

    async def retrieve_detailed(query):
        return {"candidates": [GOOD_HIT], "evidence": [GOOD_HIT]}

    async def answer(query, evidence, *, order, summary_text):
        return {
            "answer": "签收后7天内可以退货[1]",
            "refused": False,
            "citations": [{**evidence[0], "n": 1}],
            "reason": None,
        }

    services = SimpleNamespace(
        max_steps=4,
        classify=classify,
        retrieve_detailed=retrieve_detailed,
        check_sufficient=AsyncMock(return_value={"useful": True}),
        answer=answer,
        list_orders=AsyncMock(return_value=[]),
        get_order=AsyncMock(return_value=None),
        rerank_policy=AsyncMock(return_value=[GOOD_HIT]),
    )
    for key, value in overrides.items():
        setattr(services, key, value)
    return services


@pytest.fixture
def repo(monkeypatch):
    """替换节点里用到的 MySQL 写入。"""
    save_turn = AsyncMock()
    capture = AsyncMock()
    monkeypatch.setattr(nodes.repository, "save_turn", save_turn)
    monkeypatch.setattr(nodes.repository, "capture_low_confidence", capture)
    return SimpleNamespace(save_turn=save_turn, capture_low_confidence=capture)


def runtime_for(services):
    return Runtime(build_graph(services, checkpointer=InMemorySaver()))


def test_make_nodes_rejects_invalid_max_steps():
    with pytest.raises(ValueError):
        nodes.make_nodes(SimpleNamespace(max_steps=0))


class TestKnowledgeFlow:
    async def test_answer_path(self, repo):
        services = make_services()
        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")

        assert result["trace"] == ["resolve_reference", "classify", "retrieve", "answer", "finish"]
        assert result["answer"] == "签收后7天内可以退货[1]"
        assert result["citations"][0]["n"] == 1
        assert result["message_id"] == f"msg_c1_{result['request_id']}"
        assert isinstance(result["messages"][-1], AIMessage)
        assert result["messages"][-1].content == result["answer"]
        repo.save_turn.assert_awaited_once()
        repo.capture_low_confidence.assert_not_awaited()

    async def test_insufficient_evidence_falls_back(self, repo):
        services = make_services(check_sufficient=AsyncMock(return_value={"useful": False}))

        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")

        assert result["trace"][-2:] == ["fallback", "finish"]
        assert result["answer"] == nodes.REFUSAL
        assert result["fallback_reason"] == "insufficient_evidence"
        repo.capture_low_confidence.assert_awaited_once()
        assert repo.capture_low_confidence.await_args.kwargs["source"] == "self_check"

    async def test_check_error_message(self, repo):
        services = make_services(check_sufficient=AsyncMock(side_effect=TimeoutError()))

        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")

        assert result["answer"].startswith("暂时无法完成资料核对")

    async def test_snapshot_failure_does_not_break_answer(self, repo):
        repo.save_turn.side_effect = RuntimeError("db down")

        result = await runtime_for(make_services()).run_turn("退货期限是多久", "u1", "c1")

        assert result["answer"] == "签收后7天内可以退货[1]"
        assert result["message_id"] is None

    async def test_refused_answer_is_logged(self, repo):
        async def refuse(query, evidence, *, order, summary_text):
            return {"answer": "x", "refused": True, "citations": [], "reason": "grounding_failed"}

        result = await runtime_for(make_services(answer=refuse)).run_turn("退货期限", "u1", "c1")

        assert result["answer"] == nodes.REFUSAL
        assert result["citations"] == []
        assert repo.capture_low_confidence.await_args.kwargs["reason"] == "grounding_failed"


@pytest.mark.parametrize(
    "route,node,answer_prefix",
    [
        ("chat", "chat", "你好"),
        ("complaint", "complaint", "已了解你的投诉"),
        ("human", "human", "如需人工协助"),
        ("clarify", "clarify_intent", "请补充"),
    ],
)
async def test_simple_routes(repo, route, node, answer_prefix):
    result = await runtime_for(make_services(route=route)).run_turn("随便聊聊", "u1", "c1")
    assert result["trace"] == ["resolve_reference", "classify", node, "finish"]
    assert result["answer"].startswith(answer_prefix)


async def test_ambiguous_reference_asks_for_clarification(repo):
    services = make_services()
    result = await runtime_for(services).run_turn("那个订单能退吗", "u1", "c1")
    assert result["trace"] == ["resolve_reference", "clarify_reference", "finish"]


class TestRefundFlow:
    ORDER = {"order_id": "ORD-1", "user_id": "u1", "product_name": "耳机"}

    async def test_explicit_order_goes_to_policy(self, repo):
        services = make_services(route="refund", get_order=AsyncMock(return_value=self.ORDER))

        result = await runtime_for(services).run_turn("ORD-1 能退吗", "u1", "c1")

        assert result["trace"] == [
            "resolve_reference", "classify", "fetch_order", "policy", "answer", "finish",
        ]
        assert result["order"] == self.ORDER
        assert result["last_order_id"] == "ORD-1"

    async def test_other_users_order_rejected(self, repo):
        services = make_services(
            route="refund",
            get_order=AsyncMock(return_value={**self.ORDER, "user_id": "someone"}),
        )

        result = await runtime_for(services).run_turn("ORD-1 能退吗", "u1", "c1")

        assert result["trace"][-2:] == ["order_result", "finish"]
        assert result["answer"] == "没有找到属于你的这笔订单，请核对订单号。"

    async def test_multiple_orders_need_clarification(self, repo):
        result = await runtime_for(make_services(route="refund")).run_turn(
            "ORD-1 和 ORD-2 能退吗", "u1", "c1",
        )
        assert result["answer"] == "请一次只提供一个订单号。"

    async def test_select_order_interrupt_and_resume(self, repo):
        services = make_services(
            route="refund",
            list_orders=AsyncMock(return_value=[self.ORDER]),
            get_order=AsyncMock(return_value=self.ORDER),
        )
        runtime = runtime_for(services)

        first = await runtime.run_turn("我要退款", "u1", "c1")
        preview = first["__interrupt__"][0].value
        assert preview["kind"] == "select_order"
        assert preview["orders"] == [{"order_id": "ORD-1", "product_name": "耳机"}]

        # 有待处理中断时不能直接发新问题
        with pytest.raises(ValueError, match="待处理"):
            await runtime.run_turn("新问题", "u1", "c1")

        with pytest.raises(ValueError, match="卡片中的订单"):
            await runtime.run_turn(
                "", "u1", "c1",
                resume={"kind": "select_order", "request_id": preview["request_id"], "order_id": "ORD-9"},
            )

        result = await runtime.run_turn(
            "", "u1", "c1",
            resume={"kind": "select_order", "request_id": preview["request_id"], "order_id": "ORD-1"},
        )
        assert result["trace"][-3:] == ["policy", "answer", "finish"]
        services.get_order.assert_awaited_once_with("ORD-1")

    async def test_cancel_order_selection(self, repo):
        services = make_services(route="refund", list_orders=AsyncMock(return_value=[self.ORDER]))
        runtime = runtime_for(services)

        first = await runtime.run_turn("我要退款", "u1", "c1")
        request_id = first["__interrupt__"][0].value["request_id"]

        with pytest.raises(ValueError, match="过期"):
            await runtime.run_turn(
                "", "u1", "c1",
                resume={"kind": "select_order", "request_id": "stale", "cancelled": True},
            )

        result = await runtime.run_turn(
            "", "u1", "c1",
            resume={"kind": "select_order", "request_id": request_id, "cancelled": True},
        )
        assert result["answer"] == "已取消选择订单，本次没有继续处理。"


class TestAgentFlow:
    async def test_agent_without_tools_finishes(self, repo):
        services = make_services(
            route="business",
            agent=AsyncMock(return_value=AIMessage(content="请提供订单号")),
        )

        result = await runtime_for(services).run_turn("帮我查物流", "u1", "c1")

        assert result["trace"] == ["resolve_reference", "classify", "agent", "finish"]
        assert result["answer"] == "请提供订单号"
        # 业务分支不重复追加同一条回答
        assert [m.content for m in result["messages"]] == ["帮我查物流", "请提供订单号"]

    async def test_malformed_tool_call_is_rejected(self, repo):
        bad = AIMessage(content="", tool_calls=[{"id": "c1", "name": "x", "args": {}}])
        bad.tool_calls[0]["id"] = " "
        services = make_services(route="business", agent=AsyncMock(return_value=bad))

        result = await runtime_for(services).run_turn("帮我查物流", "u1", "c1")

        assert result["answer"] == "工具调用格式错误，请稍后重试。"


class TestRuntime:
    async def test_resume_without_pending_rejected(self, repo):
        with pytest.raises(ValueError, match="没有待恢复"):
            await runtime_for(make_services()).run_turn("", "u1", "c1", resume={"kind": "x"})

    async def test_threads_are_isolated_per_conversation(self, repo):
        runtime = runtime_for(make_services())
        await runtime.run_turn("退货期限是多久", "u1", "c1")
        await runtime.run_turn("退货期限是多久", "u1", "c2")
        await runtime.run_turn("还有别的吗", "u1", "c1")

        c1 = await runtime.graph.aget_state({"configurable": {"thread_id": "u1:c1"}})
        c2 = await runtime.graph.aget_state({"configurable": {"thread_id": "u1:c2"}})
        assert len(c1.values["messages"]) == 4
        assert len(c2.values["messages"]) == 2

    async def test_stream_turn_events(self, repo):
        events = [e async for e in runtime_for(make_services()).stream_turn("退货期限是多久", "u1", "c1")]

        kinds = [e.get("event", "delta" if "delta" in e else None) for e in events]
        assert kinds == ["node"] * 5 + ["citations", "delta", "done", "end"]
        assert events[6]["delta"] == "签收后7天内可以退货[1]"

    async def test_stream_turn_interrupt(self, repo):
        services = make_services(
            route="refund",
            list_orders=AsyncMock(return_value=[TestRefundFlow.ORDER]),
        )
        events = [e async for e in runtime_for(services).stream_turn("我要退款", "u1", "c1")]

        assert events[-2]["event"] == "interrupt"
        assert events[-2]["preview"]["kind"] == "select_order"
        assert events[-1] == {"event": "end"}

    async def test_stream_turn_error_still_ends(self, repo):
        async def boom(query):
            raise RuntimeError("milvus down")

        services = make_services(retrieve_detailed=boom)
        events = [e async for e in runtime_for(services).stream_turn("退货期限", "u1", "c1")]

        assert events == [{"event": "error", "message": "图执行失败"}, {"event": "end"}]

    async def test_failed_turn_must_be_retried_first(self, repo):
        calls = {"n": 0}

        async def flaky(query):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("milvus down")
            return {"candidates": [GOOD_HIT], "evidence": [GOOD_HIT]}

        runtime = runtime_for(make_services(retrieve_detailed=flaky))
        with pytest.raises(RuntimeError):
            await runtime.run_turn("退货期限", "u1", "c1")

        with pytest.raises(ValueError, match="重试失败"):
            await runtime.run_turn("别的问题", "u1", "c1")

        result = await runtime.run_turn("退货期限", "u1", "c1")
        assert result["answer"] == "签收后7天内可以退货[1]"
        assert [m.type for m in result["messages"]] == ["human", "ai"]
