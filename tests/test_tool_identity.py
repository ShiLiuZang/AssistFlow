"""
测试订单工具的身份注入和权限隔离
覆盖用户ID注入、所有权检查、tracking_no字段过滤
"""
import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.intent import Intent, Prediction
from app.graph.adapters import make_services, order_tool
from app.graph.build import build_graph
from app.graph.runtime import Runtime
from app.tools.context import ToolContext
from app.tools.orders import (
    get_order,
    get_user_order,
    get_user_tracking_no,
    list_user_orders,
)
from app.tools.registry import Registry


def test_user_order_lookup_returns_owned_tracking_mapping_only():
    """测试用户订单查询：仅返回归属订单，不暴露tracking_no映射"""
    owned = get_user_order("ORD-1001", "u1")

    assert owned is not None
    assert "tracking_no" not in owned
    assert get_user_order("ORD-1001", "u2") is None
    assert get_user_order("ORD-9999", "u1") is None
    assert get_user_tracking_no("ORD-1001", "u1") == "SF-DEMO-1001"
    assert get_user_tracking_no("ORD-1001", "u2") is None
    assert get_user_tracking_no("ORD-9999", "u1") is None
    assert "tracking_no" not in get_order("ORD-1001")
    assert all("tracking_no" not in order for order in list_user_orders("u1"))


def test_order_identity_is_injected_and_ownership_is_checked():
    """测试身份注入：自动注入user_id并检查所有权"""
    context = ToolContext(user_id="u1", conversation_id="conversation-1")

    owned = asyncio.run(order_tool({"order_id": "ORD-1001"}, context, "call-1"))
    assert owned["found"] is True
    assert owned["product_name"] == "保温杯"

    other = asyncio.run(order_tool({"order_id": "ORD-1002"}, context, "call-2"))
    missing = asyncio.run(order_tool({"order_id": "ORD-9999"}, context, "call-3"))
    assert other == missing == {
        "found": False,
        "error": "没有找到您的这笔订单",
        "code": "order_not_owned",
    }

    spoofed = asyncio.run(order_tool(
        {"order_id": "ORD-1001", "user_id": "u2"}, context, "call-4"
    ))
    assert spoofed == owned


def test_runtime_passes_conversation_context_to_order_tool():
    """测试运行时上下文传递：会话ID和用户ID正确传递到工具"""
    async def run():
        services = make_services()
        handler = AsyncMock(side_effect=order_tool)
        spec = services.registry.get("query_order")
        registry = Registry()
        registry.register(replace(spec, invoke=handler))
        services.registry = registry
        services.classify = AsyncMock(return_value=(
            Prediction(intent=Intent.ORDER, confidence=0.95), "business",
        ))
        services.agent = AsyncMock(side_effect=[
            AIMessage(content="", tool_calls=[{
                "id": "call-context", "name": "query_order", "args": {"order_id": "ORD-1001"},
            }]),
            AIMessage(content="订单已发货"),
        ])
        result = await Runtime(build_graph(services, InMemorySaver())).run_turn(
            "查订单 ORD-1001", "u1", "conversation-context",
        )
        handler.assert_awaited_once_with(
            {"order_id": "ORD-1001"}, ToolContext("u1", "conversation-context"), "call-context",
        )
        messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
        assert len(messages) == 1 and messages[0].tool_call_id == "call-context"
        assert messages[0].status == "success"
        assert json.loads(messages[0].content)["found"] is True
        assert result["last_order_id"] == "ORD-1001"
    asyncio.run(run())
