"""显式运行的 MCP 本地 HTTP 验收；仅使用合成订单，不调用模型或数据库。"""

import asyncio
import json
import socket

from app.graph.adapters import make_services_with_mcp
from app.tools.context import ToolContext
from app.tools.engine import execute_tool_call
from app.tools.mcp_client import StreamableHTTPTransport


URLS = {
    "logistics": "http://127.0.0.1:18101/mcp",
    "aftersales": "http://127.0.0.1:18102/mcp",
}
REMOTE_TOOLS = ("query_logistics", "query_warranty", "query_return_status")
CONTEXT = ToolContext("u1", "mcp-http-verification")


class RecordingTransport(StreamableHTTPTransport):
    def __init__(self, urls):
        super().__init__(urls)
        self.calls = []

    async def call_tool(self, server, name, args):
        self.calls.append((server, name, dict(args)))
        return await super().call_tool(server, name, args)


async def verify():
    transport = RecordingTransport(URLS)
    services, issues = await make_services_with_mcp(transport, list(URLS))
    assert not issues, issues
    registry = services.registry
    assert registry is not None
    model_names = {
        item["function"]["name"]
        for item in services.agent.keywords["model_tools"]
    }
    assert model_names == set(services.tools)
    assert set(REMOTE_TOOLS) <= model_names
    assert {"query_order", "create_ticket"} <= model_names

    results = {}
    for name in REMOTE_TOOLS:
        run = await execute_tool_call(
            {"id": name, "name": name, "args": {"order_id": "ORD-1001"}},
            CONTEXT, registry,
        )
        assert run.ok, (name, run.status, run.data)
        results[name] = run.data

    assert results["query_logistics"]["status_code"] == "IN_TRANSIT"
    assert results["query_logistics"]["tracking_no"] == "SF-DEMO-1001"
    assert results["query_warranty"]["warranty"] == "在保"
    assert results["query_return_status"]["return_status"] == "无退货记录"
    assert transport.calls == [
        ("logistics", "query_logistics", {"tracking_no": "SF-DEMO-1001"}),
        ("aftersales", "query_warranty", {"order_id": "ORD-1001"}),
        ("aftersales", "query_return_status", {"order_id": "ORD-1001"}),
    ]

    for name in REMOTE_TOOLS:
        for order_id in ("ORD-1002", "ORD-9999"):
            run = await execute_tool_call(
                {"id": f"denied-{name}-{order_id}", "name": name,
                 "args": {"order_id": order_id}},
                CONTEXT, registry,
            )
            assert run.status == "business_error", run
            assert run.data["code"] == "order_not_owned", run

    for extra in ({"user_id": "u2"}, {"tracking_no": "FORGED"}):
        run = await execute_tool_call(
            {"id": "spoof", "name": "query_logistics",
             "args": {"order_id": "ORD-1001", **extra}},
            CONTEXT, registry,
        )
        assert run.status == "invalid_args", run
    assert len(transport.calls) == 3, transport.calls


    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        port = unavailable.getsockname()[1]
        degraded = RecordingTransport({
            **URLS, "logistics": f"http://127.0.0.1:{port}/mcp",
        })
        remaining, problems = await make_services_with_mcp(degraded, list(URLS))
        assert len(problems) == 1, problems
        assert problems[0]["server"] == "logistics", problems
        assert problems[0]["code"] == "discovery_failed", problems
        assert "query_logistics" not in remaining.tools
        assert "query_warranty" in remaining.tools
        assert "query_order" in remaining.tools
        for name in ("query_warranty", "query_order"):
            run = await execute_tool_call(
                {"id": f"degraded-{name}", "name": name,
                 "args": {"order_id": "ORD-1001"}},
                CONTEXT, remaining.registry,
            )
            assert run.ok, (name, run.status, run.data)

    print(json.dumps({
        "http_results": results,
        "ownership_denials": 6,
        "spoofed_argument_denials": 2,
        "denied_remote_calls": 0,
        "unreachable_endpoint_degradation": "passed",
        "scope": "local HTTP, synthetic data; no model/database/browser acceptance",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(verify(), timeout=45))
