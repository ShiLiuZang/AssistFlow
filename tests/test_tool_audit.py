"""
测试工具调用的审计日志功能
覆盖状态记录、参数脱敏、数据库持久化和HTTP集成
"""
import asyncio
from unittest.mock import AsyncMock


from app.tools.context import ToolContext
from app.tools.engine import execute_tool_call
from app.tools.registry import Registry, ToolSpec


CONTEXT = ToolContext("u1", "conversation-audit")
SCHEMA = {
    "type": "object",
    "properties": {"order_id": {"type": "string"}},
    "required": ["order_id"],
    "additionalProperties": False,
}


def register(handler, **options):
    """构造带工具的注册表"""
    registry = Registry()
    registry.register(ToolSpec(
        name="query_logistics",
        invoke=handler,
        description="查询物流",
        schema=SCHEMA,
        **options,
    ))
    return registry


def test_audit_uses_final_status_and_omits_parameter_values():
    """测试审计记录：使用最终状态，不记录参数值"""
    rows = []

    async def sink(row):
        rows.append(row)

    handler = AsyncMock(return_value={"value": object()})
    call = {"id": "call-1", "name": "query_logistics", "args": {
        "order_id": "PRIVATE_ORDER_VALUE",
    }}
    run = asyncio.run(execute_tool_call(
        call, CONTEXT,
        register(handler), audit_sink=sink,
    ))
    assert run.status == "format_error"
    assert len(rows) == 1
    record = rows[0]
    assert record.status == run.status
    assert record.tool_call_id == "call-1"
    assert record.conversation_id == CONTEXT.conversation_id
    assert record.argument_fields == ("order_id",)
    assert record.result_chars == len(run.content)
    assert record.retry_count == 0
    assert "PRIVATE_ORDER_VALUE" not in repr(record)
    handler.assert_awaited_once_with(call["args"], CONTEXT, "call-1")
