"""app.tools：注册表校验、调用检查、受控执行（超时/重试/错误分类）与审计。"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import ValidationError

from app.tools import audit, engine
from app.tools.context import ToolContext
from app.tools.registry import Registry, ToolSpec, validate_args

SCHEMA = {
    "type": "object",
    "properties": {"order_id": {"type": "string", "minLength": 1}},
    "required": ["order_id"],
    "additionalProperties": False,
}
CONTEXT = ToolContext(user_id="u1", conversation_id="c1")


def spec(**overrides):
    values = {
        "name": "query_order",
        "invoke": AsyncMock(return_value={"found": True}),
        "description": "查询订单",
        "schema": SCHEMA,
    }
    values.update(overrides)
    return ToolSpec(**values)


def call(name="query_order", args=None, call_id="c1"):
    return {"id": call_id, "name": name, "args": {"order_id": "ORD-1"} if args is None else args}


class TestRegistry:
    def test_register_and_describe(self):
        registry = Registry()
        registry.register(spec())

        assert registry.get("query_order").description == "查询订单"
        assert registry.get("missing") is None
        assert registry.model_tools() == [{
            "type": "function",
            "function": {"name": "query_order", "description": "查询订单", "parameters": SCHEMA},
        }]
        assert set(registry.execution_tools()) == {"query_order"}

    def test_schema_is_copied(self):
        schema = json.loads(json.dumps(SCHEMA))
        registry = Registry()
        registry.register(spec(schema=schema))
        schema["required"] = []
        registry.model_tools()[0]["function"]["parameters"]["required"].append("x")
        assert registry.get("query_order").schema["required"] == ["order_id"]

    @pytest.mark.parametrize(
        "overrides,message",
        [
            ({"name": " "}, "名称"),
            ({"description": ""}, "描述"),
            ({"schema": {"type": "array"}}, "对象"),
            ({"schema": {"type": "object"}}, "额外字段"),
            ({"permission": "admin"}, "权限"),
            ({"timeout": 0}, "timeout"),
            ({"timeout": True}, "timeout"),
            ({"timeout": float("inf")}, "timeout"),
            ({"max_retries": -1}, "max_retries"),
            ({"max_retries": 1.0}, "max_retries"),
            ({"source": "remote"}, "来源"),
            ({"server": "x"}, "内置工具"),
            ({"source": "mcp"}, "MCP"),
            ({"source": "mcp", "server": " "}, "MCP"),
        ],
    )
    def test_rejects_invalid_spec(self, overrides, message):
        with pytest.raises(ValueError, match=message):
            Registry().register(spec(**overrides))

    def test_rejects_duplicate(self):
        registry = Registry()
        registry.register(spec())
        with pytest.raises(ValueError, match="已注册"):
            registry.register(spec())

    def test_validate_args(self):
        validate_args(spec(), {"order_id": "ORD-1"})
        with pytest.raises(ValidationError):
            validate_args(spec(), {"order_id": ""})


@pytest.mark.parametrize(
    "data,status",
    [
        ({"found": True}, "success"),
        ({"code": "order_not_owned", "error": "x"}, "business_error"),
        ({"code": "timeout"}, "timeout"),
        ({"cancelled": True}, "permission_denied"),
        ({"confirmed": False}, "permission_denied"),
        ({"error": "库存不足"}, "business_error"),
        ({"code": 1}, "format_error"),
        ([1], "format_error"),
        ({"code": "custom"}, "success"),
    ],
)
def test_classify_tool_result(data, status):
    assert engine.classify_tool_result(data) == status


class TestMakeToolRun:
    def test_success_is_reclassified(self):
        run = engine.make_tool_run(call(), "success", {"error": "x"})
        assert (run.status, run.ok, run.tool_call_id, run.name) == ("business_error", False, "c1", "query_order")
        assert json.loads(run.content) == {"error": "x"}

    def test_non_serializable_becomes_format_error(self):
        run = engine.make_tool_run(call(), "success", {"value": float("nan")})
        assert run.status == "format_error"
        assert run.data["code"] == "format_error"

    def test_explicit_error_status_kept(self):
        assert engine.make_tool_run({}, "timeout", {"code": "timeout"}).status == "timeout"


class TestCheckToolCall:
    @pytest.fixture
    def registry(self):
        registry = Registry()
        registry.register(spec())
        return registry

    def test_valid(self, registry):
        found, error = engine.check_tool_call(call(), registry)
        assert (found.name, error) == ("query_order", None)

    @pytest.mark.parametrize(
        "bad",
        [None, {"id": "", "name": "query_order", "args": {}}, {"id": "c", "name": " ", "args": {}},
         {"id": "c", "name": "query_order", "args": []}],
    )
    def test_invalid_call(self, registry, bad):
        assert engine.check_tool_call(bad, registry) == (None, {
            "code": "invalid_call", "error": "工具调用必须包含有效的 id、name 和对象 args",
        })

    def test_unknown_tool(self, registry):
        assert engine.check_tool_call(call("nope"), registry)[1]["code"] == "unknown_tool"

    def test_invalid_args(self, registry):
        found, error = engine.check_tool_call(call(args={"order_id": "x", "extra": 1}), registry)
        assert found is not None
        assert error["code"] == "invalid_args"

    def test_broken_schema(self, registry, monkeypatch):
        monkeypatch.setattr(engine, "validate_args", lambda s, a: (_ for _ in ()).throw(RuntimeError()))
        assert engine.check_tool_call(call(), registry)[1]["code"] == "invalid_schema"


class TestExecuteToolCall:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        sleep = AsyncMock()
        monkeypatch.setattr(engine.asyncio, "sleep", sleep)
        return sleep

    def registry_with(self, invoke, **overrides):
        registry = Registry()
        registry.register(spec(invoke=invoke, **overrides))
        return registry

    async def test_success_passes_args_context_and_call_id(self):
        invoke = AsyncMock(return_value={"found": True})
        run = await engine.execute_tool_call(call(), CONTEXT, self.registry_with(invoke))

        assert run.ok
        assert invoke.await_args.args == ({"order_id": "ORD-1"}, CONTEXT, "c1")

    async def test_invalid_call_never_invokes(self):
        invoke = AsyncMock()
        run = await engine.execute_tool_call({"id": 1}, CONTEXT, self.registry_with(invoke))
        assert (run.status, run.tool_call_id, run.name) == ("invalid_call", "", "")
        invoke.assert_not_awaited()

    async def test_write_tools_blocked(self):
        invoke = AsyncMock()
        run = await engine.execute_tool_call(call(), CONTEXT, self.registry_with(invoke, permission="write"))
        assert run.status == "permission_denied"
        invoke.assert_not_awaited()

    async def test_transient_errors_retried(self, no_sleep):
        invoke = AsyncMock(side_effect=[ConnectionError(), TimeoutError(), {"found": True}])
        run = await engine.execute_tool_call(call(), CONTEXT, self.registry_with(invoke, max_retries=2))
        assert (run.status, run.retry_count) == ("success", 2)
        assert [c.args[0] for c in no_sleep.await_args_list] == [0.1, 0.2]

    @pytest.mark.parametrize("error,status", [(TimeoutError(), "timeout"), (ConnectionError(), "transport_error")])
    async def test_retries_exhausted(self, error, status):
        invoke = AsyncMock(side_effect=error)
        run = await engine.execute_tool_call(call(), CONTEXT, self.registry_with(invoke, max_retries=1))
        assert (run.status, run.retry_count, invoke.await_count) == (status, 1, 2)

    async def test_real_timeout(self):
        async def slow(*args):
            await asyncio.Event().wait()

        run = await engine.execute_tool_call(call(), CONTEXT, self.registry_with(slow, timeout=0.01))
        assert run.status == "timeout"

    @pytest.mark.parametrize(
        "error,status",
        [
            (engine.BusinessError("x"), "business_error"),
            (engine.ToolResultFormatError("x"), "format_error"),
            (KeyError("x"), "execution_error"),
        ],
    )
    async def test_errors_not_retried(self, error, status):
        invoke = AsyncMock(side_effect=error)
        run = await engine.execute_tool_call(call(), CONTEXT, self.registry_with(invoke, max_retries=3))
        assert run.status == status
        assert invoke.await_count == 1

    async def test_non_dict_result(self):
        run = await engine.execute_tool_call(call(), CONTEXT, self.registry_with(AsyncMock(return_value=[1])))
        assert run.status == "format_error"

    async def test_audit_record_written(self):
        records = []

        async def sink(record):
            records.append(record)

        await engine.execute_tool_call(
            call(args={"order_id": "ORD-1"}), CONTEXT,
            self.registry_with(AsyncMock(return_value={"found": True})), audit_sink=sink,
        )

        record = records[0]
        assert (record.tool_name, record.status, record.source, record.conversation_id) == (
            "query_order", "success", "builtin", "c1",
        )
        assert record.argument_fields == ("order_id",)


class TestAudit:
    def test_build_tool_audit_hides_values_and_unknown_fields(self):
        run = engine.make_tool_run(call(), "success", {"found": True})
        record = audit.build_tool_audit(
            {"args": {"order_id": "ORD-1", "secret": "x", 1: "y"}}, CONTEXT, run, None,
        )
        assert record.argument_fields == ("order_id",)
        assert (record.source, record.server) == ("unknown", None)
        assert record.result_chars == len(run.content)

    def test_build_ticket_decision_audit(self):
        record = audit.build_ticket_decision_audit(
            {"id": "c9", "args": {"ticket_type": "退款", "description": "坏了"}}, 7, {"confirmed": False}, 12,
        )
        assert (record.status, record.audit_key, record.argument_fields) == (
            "permission_denied", "ticket-decision:7:c9", ("description", "ticket_type"),
        )
        with pytest.raises(ValueError):
            audit.build_ticket_decision_audit({"id": "c"}, 1, {"confirmed": "yes"}, 0)

    async def test_emit_swallows_failures(self, caplog):
        record = audit.build_ticket_decision_audit({"id": "c"}, 1, {"confirmed": True}, 0)

        async def failing(record):
            raise RuntimeError("db down")

        await audit.emit_tool_audit(None, record)
        await audit.emit_tool_audit(failing, record)
        assert "工具审计写入失败" in caplog.text

    async def test_emit_propagates_cancellation(self):
        record = audit.build_ticket_decision_audit({"id": "c"}, 1, {"confirmed": True}, 0)

        async def cancelled(record):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await audit.emit_tool_audit(cancelled, record)
