"""
测试图节点的独立功能
覆盖共指消解优先级、模糊引用的澄清中断
"""
from types import SimpleNamespace

import asyncio

from app.graph.nodes import make_nodes
from app.graph.build import build_graph
from app.graph.runtime import Runtime
from langgraph.checkpoint.memory import InMemorySaver
from unittest.mock import AsyncMock


class Services:
    max_steps = 1


def test_resolve_reference_prefers_verified_last_order():
    """测试共指消解优先级：last_order_id优先于selected_order"""
    nodes = make_nodes(Services())
    state = {
        "query": "这个订单能退吗？",
        "messages": [],
        "last_order_id": "ORD-1001",
        "selected_order": "ORD-1002",
        "trace": [],
    }
    result = asyncio.run(nodes["resolve_reference"](state))
    assert result["resolved_query"] == "ORD-1001能退吗？"
    assert result["query"] == "这个订单能退吗？"
    assert result["trace"] == ["resolve_reference"]


def test_ambiguous_reference_stops_before_classify_and_retrieve():
    """测试模糊引用：触发澄清节点，跳过分类和检索"""
    async def run():
        services = SimpleNamespace(
            max_steps=1,
            classify=AsyncMock(return_value="knowledge"),
            retrieve=AsyncMock(return_value=[]),
            answer=AsyncMock(),
            agent=AsyncMock(),
            tools={},
            list_orders=AsyncMock(),
            get_order=AsyncMock(),
            expand_policy=AsyncMock(return_value=[]),
        )
        runtime = Runtime(build_graph(services, InMemorySaver()))
        result = await runtime.run_turn("这个订单能退吗？", "u1", "clarify-test")
        assert result["answer"] == "请说明你指的是哪个订单或商品。"
        assert result["trace"] == [
            "resolve_reference", "clarify_reference", "finish"
        ]
        services.classify.assert_not_awaited()
        services.retrieve.assert_not_awaited()
        services.agent.assert_not_awaited()
    asyncio.run(run())
