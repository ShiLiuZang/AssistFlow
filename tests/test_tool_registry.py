"""
测试工具注册表的注册、查询和Schema隔离
覆盖重复注册拒绝、Schema深拷贝、model_tools转换
"""
import asyncio

import pytest

from app.graph.adapters import order_tool
from app.tools.context import ToolContext
from app.tools.order_tools import query_order
from app.tools.registry import Registry, ToolSpec


def test_register_and_query_order():
    """测试工具注册和查询：注册后可调用，重复注册被拒绝"""
    registry = Registry()
    schema = query_order.tool_call_schema.model_json_schema()
    schema["additionalProperties"] = False
    spec = ToolSpec(
        "query_order",
        order_tool,
        query_order.description,
        schema,
    )
    registry.register(spec)

    found = registry.get("query_order")
    assert found is not None
    assert found.invoke is order_tool
    assert found.schema == spec.schema
    assert registry.get("missing") is None

    result = asyncio.run(found.invoke(
        {"order_id": "ORD-1001"}, ToolContext("u1", "conversation-1"), "call-1"
    ))
    assert result["found"] is True
    assert result["product_name"] == "保温杯"
    assert result["status"] == "已发货"

    with pytest.raises(ValueError, match="已注册"):
        registry.register(spec)
    with pytest.raises(ValueError, match="不能为空"):
        registry.register(ToolSpec("  ", order_tool, "订单查询", {}))


def test_model_schema_is_a_copy():
    """测试Schema隔离：注册后修改不影响内部存储和model_tools输出"""
    schema = {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "additionalProperties": False,
    }
    registry = Registry()
    registry.register(ToolSpec("query_order", order_tool, "订单查询", schema))

    schema["properties"]["order_id"]["type"] = "integer"
    model_tools = registry.model_tools()
    assert (
        model_tools[0]["function"]["parameters"]["properties"]["order_id"]["type"]
        == "string"
    )

    model_tools[0]["function"]["parameters"]["properties"]["order_id"]["type"] = "number"
    assert registry.get("query_order").schema["properties"]["order_id"]["type"] == "string"
    assert (
        registry.model_tools()[0]["function"]["parameters"]["properties"]["order_id"]["type"]
        == "string"
    )
