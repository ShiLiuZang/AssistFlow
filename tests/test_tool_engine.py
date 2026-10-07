"""
测试工具引擎的执行和状态恢复
覆盖错误分类、状态一致性、重复ID检测和业务错误处理
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.api.graph_chat import restore_messages
from app.core.intent import Intent, Prediction
from app.graph.adapters import make_services, make_tool_registry
from app.graph.build import build_graph
from app.graph.runtime import Runtime
from app.tools.context import ToolContext
from app.tools.engine import execute_tool_call
from app.tools.registry import Registry, ToolSpec


CONTEXT = ToolContext("u1", "engine-test")
SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def register(handler):
    registry = Registry()
    registry.register(ToolSpec("demo", handler, "测试工具", SCHEMA))
    return registry


@pytest.mark.parametrize("data, expected", [
    ({"code": []}, "format_error"),
    ({"code": {}}, "format_error"),
    ({"code": 123}, "format_error"),
    ({"error": "service unavailable"}, "business_error"),
    ({"cancelled": True}, "permission_denied"),
    ({"confirmed": False}, "permission_denied"),
    ({"code": "execution_error"}, "execution_error"),
    ({"found": True}, "success"),
    ({"code": None}, "success"),
])
def test_execution_and_restoration_agree(data, expected):
    """测试执行与恢复的状态一致性"""
    handler = AsyncMock(return_value=data)
    run = asyncio.run(execute_tool_call(
        {"id": "a", "name": "demo", "args": {}}, CONTEXT, register(handler),
    ))
    assert run.status == expected
    record = SimpleNamespace(role="tool", content=run.content, tool_call_id="a")
    message = restore_messages([record])[0]
    assert message.status == ("success" if run.ok else "error")
    assert message.tool_call_id == "a"
    handler.assert_awaited_once()


def test_duplicate_ids_rejected_before_tools():
    """测试重复ID检测：在调用工具前拒绝重复的call_id"""
    async def run():
        services = make_services()
        services.classify = AsyncMock(return_value=(
            Prediction(intent=Intent.ORDER, confidence=0.95), "business",
        ))
        services.agent = AsyncMock(return_value=AIMessage(content="", tool_calls=[
            {"id": "same", "name": "query_order", "args": {"order_id": "ORD-1001"}},
            {"id": "same", "name": "create_ticket", "args": {"ticket_type": "退款"}},
        ]))
        order_tool = AsyncMock()
        services.registry = Registry()
        spec = make_tool_registry().get("query_order")
        services.registry.register(ToolSpec(
            spec.name, order_tool, spec.description, spec.schema,
        ))
        result = await Runtime(build_graph(services, InMemorySaver())).run_turn(
            "查询订单", "u1", "duplicate-test",
        )
        assert result["trace"] == ["resolve_reference", "classify", "agent", "finish"]
        assert "格式错误" in result["answer"]
        assert not any(isinstance(message, ToolMessage) for message in result["messages"])
        order_tool.assert_not_awaited()
    asyncio.run(run())
