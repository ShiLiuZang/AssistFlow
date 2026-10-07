"""
测试主图的端到端流程回归
使用假服务和一次性SQLite，覆盖所有意图分支
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.intent import Intent, Prediction, ROUTES
from app.graph.build import build_graph
from app.graph.runtime import Runtime
from app.graph.adapters import make_tool_registry


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
