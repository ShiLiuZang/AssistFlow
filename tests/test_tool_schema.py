"""
测试工具Schema的验证和引用解析
覆盖非法参数拒绝、本地$ref支持、外部引用拒绝
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema.exceptions import ValidationError
from langchain_core.messages import AIMessage, ToolMessage

from app.graph.adapters import make_tool_registry
from app.graph.nodes import make_nodes
from app.tools.registry import Registry, ToolSpec, validate_args


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("create_ticket", {"ticket_type": "退款"}),
        ("create_ticket", {"ticket_type": "退款", "description": ""}),
        (
            "create_ticket",
            {"ticket_type": "退款", "description": "商品破损", "confirmed": True},
        ),
        ("query_order", {"order_id": 123}),
        ("query_order", {"order_id": ""}),
        ("query_order", {"order_id": "ORD-1001", "user_id": "other"}),
    ],
)
def test_schema_rejects_bad_values_and_extra_fields(name, args):
    """测试Schema验证：拒绝非法值和额外字段"""
    spec = make_tool_registry().get(name)
    with pytest.raises(ValidationError):
        validate_args(spec, args)


def test_schema_allows_local_defs_but_not_unresolved_external_refs(monkeypatch):
    """测试Schema引用：支持本地$ref，拒绝未解析的外部引用"""
    registry = Registry()
    schema = {
        "type": "object",
        "$defs": {"text": {"type": "string"}},
        "properties": {"description": {"$ref": "#/$defs/text"}},
        "required": ["description"],
        "additionalProperties": False,
    }
    registry.register(ToolSpec("local", AsyncMock(), "本地引用", schema))
    validate_args(registry.get("local"), {"description": "商品破损"})
    with pytest.raises(ValidationError):
        validate_args(registry.get("local"), {"description": 123})

    schema["properties"]["description"]["$ref"] = "https://example.invalid/schema"
    registry.register(ToolSpec("remote", AsyncMock(), "外部引用", schema))
    network = AsyncMock(side_effect=AssertionError("unexpected network request"))
    monkeypatch.setattr("urllib.request.urlopen", network)
    with pytest.raises(Exception, match="example.invalid") as error:
        validate_args(registry.get("remote"), {"description": "商品破损"})
    assert not isinstance(error.value, ValidationError)
    network.assert_not_called()


@pytest.mark.parametrize(
    ("args", "code"),
    [
        ({"ticket_type": "退款"}, "invalid_args"),
        ({"ticket_type": "退款", "description": ""}, "invalid_args"),
        ({"ticket_type": "退款", "description": "商品破损", "confirmed": True}, "invalid_args"),
    ],
)
def test_bad_ticket_args_are_rejected_before_interrupt(args, code, monkeypatch):
    """非法参数必须产生工具错误消息，不能进入工单确认中断。"""
    interrupt = AsyncMock(side_effect=AssertionError("非法参数不得请求确认"))
    monkeypatch.setattr("app.graph.nodes.interrupt", interrupt)
    services = SimpleNamespace(max_steps=3, registry=make_tool_registry())
    message = AIMessage(content="", tool_calls=[{
        "id": "bad-ticket", "name": "create_ticket", "args": args,
    }])
    result = asyncio.run(make_nodes(services)["tools"]({
        "messages": [message], "user_id": "u1", "conversation_id": "schema-test",
    }))
    assert len(result["messages"]) == 1
    tool_message = result["messages"][0]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.tool_call_id == "bad-ticket"
    assert tool_message.status == "error"
    assert json.loads(tool_message.content)["code"] == code
    interrupt.assert_not_called()
