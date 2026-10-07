"""
测试主图的端到端流程回归
使用假服务和一次性SQLite，覆盖所有意图分支
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
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
