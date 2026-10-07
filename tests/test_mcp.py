"""
测试MCP协议的发现、调用和错误处理
覆盖工具注册、参数路由、格式化处理和业务错误映射
"""
import asyncio
import json


from app.tools.context import ToolContext
from app.tools.engine import (
    execute_tool_call,
)
from app.tools.mcp_client import discover_mcp_tools
from app.tools.registry import Registry


def tool_definition(name):
    """构造MCP工具定义"""
    parameter = "tracking_no" if name == "query_logistics" else "order_id"
    return {
        "name": name,
        "description": f"测试工具 {name}",
        "inputSchema": {
            "type": "object",
            "properties": {parameter: {"type": "string", "minLength": 1}},
            "required": [parameter],
            "additionalProperties": False,
        },
    }


class FakeTransport:
    """假传输层：模拟MCP服务器响应"""
    def __init__(self, catalogs=None, failures=None):
        self.catalogs = catalogs or {}
        self.failures = failures or {}
        self.calls = []

    async def list_tools(self, server):
        if server in self.failures:
            raise self.failures[server]
        return self.catalogs.get(server, [])

    async def call_tool(self, server, name, args):
        self.calls.append((server, name, args))
        if name == "query_logistics":
            return {"tracking_no": args["tracking_no"], "status_code": "IN_TRANSIT"}
        return {"server": server, "name": name}


def test_discovery_registers_all_servers_and_routes_calls():
    """测试工具发现：注册所有服务器的工具并路由调用"""
    transport = FakeTransport({
        "logistics": [tool_definition("query_logistics")],
        "aftersales": [tool_definition("query_warranty")],
    })
    registry = Registry()

    async def run():
        issues = await discover_mcp_tools(registry, transport, ["logistics", "aftersales"])
        assert issues == []
        assert {tool["function"]["name"] for tool in registry.model_tools()} == {
            "query_logistics", "query_warranty",
        }
        for name, server in [("query_logistics", "logistics"), ("query_warranty", "aftersales")]:
            spec = registry.get(name)
            assert spec is not None
            assert (spec.source, spec.server, spec.permission) == ("mcp", server, "read")
            assert set(spec.schema["properties"]) == {"order_id"}
            assert spec.schema["required"] == ["order_id"]

        context = ToolContext("u1", "mcp-test")
        logistics = await execute_tool_call(
            {"id": "logistics-1", "name": "query_logistics", "args": {"order_id": "ORD-1001"}},
            context, registry,
        )
        warranty = await execute_tool_call(
            {"id": "warranty-1", "name": "query_warranty", "args": {"order_id": "ORD-1001"}},
            context, registry,
        )
        assert logistics.status == warranty.status == "success"
        assert json.loads(logistics.content) == {
            "tracking_no": "SF-DEMO-1001", "status_code": "IN_TRANSIT", "status": "运输中",
        }
        assert json.loads(warranty.content) == {"server": "aftersales", "name": "query_warranty"}
        assert transport.calls == [
            ("logistics", "query_logistics", {"tracking_no": "SF-DEMO-1001"}),
            ("aftersales", "query_warranty", {"order_id": "ORD-1001"}),
        ]

    asyncio.run(run())
