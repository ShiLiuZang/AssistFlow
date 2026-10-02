"""演示订单、模型可调用工具、结果格式化与 MCP 工具发现（远端传输为替身）。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.types import TextContent

from app.tools import engine, formatting, mcp_client, orders
from app.tools.context import ToolContext
from app.tools.order_tools import query_order
from app.tools.registry import Registry, ToolSpec
from app.tools.ticket_tools import create_ticket

U1 = ToolContext(user_id="u1", conversation_id="c1")


class TestDemoOrders:
    def test_get_order_returns_copy(self):
        order = orders.get_order("ORD-1001")
        order["status"] = "改了"
        assert orders.get_order("ORD-1001")["status"] == "已发货"
        assert orders.get_order("ORD-404") is None

    def test_ownership_checks(self):
        assert orders.get_user_order("ORD-1001", "u1")["product_name"] == "保温杯"
        assert orders.get_user_order("ORD-1001", "u2") is None
        assert orders.get_user_tracking_no("ORD-1001", "u1") == "SF-DEMO-1001"
        assert orders.get_user_tracking_no("ORD-1001", "u2") is None
        assert [o["order_id"] for o in orders.list_user_orders("u2")] == ["ORD-1002"]
        assert orders.list_user_orders("nobody") == []


class TestModelTools:
    async def test_query_order_own(self):
        assert await query_order.ainvoke({"order_id": "ORD-1001", "user_id": "u1"}) == {
            "found": True, "order_id": "ORD-1001", "product_name": "保温杯", "status": "已发货",
        }

    @pytest.mark.parametrize("order_id,user", [("ORD-1001", "u2"), ("ORD-404", "u1")])
    async def test_query_order_hides_other_users(self, order_id, user):
        result = await query_order.ainvoke({"order_id": order_id, "user_id": user})
        assert result["code"] == "order_not_owned"
        assert engine.classify_tool_result(result) == "business_error"

    def test_user_id_not_exposed_to_model(self):
        assert "user_id" not in query_order.tool_call_schema.model_json_schema()["properties"]

    async def test_create_ticket_only_previews(self):
        assert await create_ticket.ainvoke({"ticket_type": "退款", "description": "坏了"}) == {
            "requires_confirmation": True, "ticket_type": "退款", "description": "坏了",
        }


class TestFormatLogistics:
    def test_known_status(self):
        assert formatting.format_logistics_result({"status_code": "IN_TRANSIT", "tracking_no": "SF1", "x": 1}) == {
            "status_code": "IN_TRANSIT", "status": "运输中", "tracking_no": "SF1",
        }

    def test_unknown_status_passthrough(self):
        assert formatting.format_logistics_result({"status_code": "DONE"}) == {"status_code": "DONE", "status": "DONE"}

    @pytest.mark.parametrize("data", [{}, {"status_code": " "}, {"status_code": "X", "tracking_no": 1}])
    def test_rejects_bad_payload(self, data):
        with pytest.raises(ValueError):
            formatting.format_logistics_result(data)


REMOTE_SCHEMA = {"type": "object", "properties": {"tracking_no": {"type": "string"}}, "required": ["tracking_no"]}
ORDER_SCHEMA = {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}


class FakeTransport:
    def __init__(self, catalogs, results=None):
        self.catalogs = catalogs
        self.results = results or {}
        self.calls = []

    async def list_tools(self, server):
        catalog = self.catalogs[server]
        if isinstance(catalog, Exception):
            raise catalog
        return catalog

    async def call_tool(self, server, name, args):
        self.calls.append((server, name, args))
        return self.results[(server, name)]


class TestDiscoverMcpTools:
    async def test_registers_allowlisted_tools_and_reports_issues(self):
        registry = Registry()
        registry.register(ToolSpec(name="query_warranty", invoke=AsyncMock(), description="d",
                                   schema={"type": "object", "additionalProperties": False}))
        transport = FakeTransport({
            "logistics": [
                {"name": "query_logistics", "description": "", "inputSchema": REMOTE_SCHEMA},
                {"name": "delete_everything", "inputSchema": REMOTE_SCHEMA},
                {"name": "", "inputSchema": {}},
            ],
            "aftersales": [
                {"name": "query_warranty", "inputSchema": ORDER_SCHEMA},
                {"name": "query_return_status", "inputSchema": {"type": "array"}},
            ],
            "down": ConnectionError("refused"),
            "weird": {"not": "a list"},
        })

        issues = await mcp_client.discover_mcp_tools(
            registry, transport, ["logistics", "aftersales", "down", "weird"],
        )

        assert {(i["server"], i["code"]) for i in issues} == {
            ("logistics", "not_allowlisted"),
            ("logistics", "registration_failed"),
            ("aftersales", "name_collision"),
            ("aftersales", "registration_failed"),
            ("down", "discovery_failed"),
            ("weird", "invalid_catalog"),
        }
        tool = registry.get("query_logistics")
        assert (tool.source, tool.server, tool.permission) == ("mcp", "logistics", "read")
        assert tool.schema == mcp_client.ORDER_QUERY_SCHEMA

    async def test_discovery_timeout(self):
        class Slow(FakeTransport):
            async def list_tools(self, server):
                import asyncio
                await asyncio.sleep(1)

        issues = await mcp_client.discover_mcp_tools(Registry(), Slow({}), ["x"], discovery_timeout=0.01)
        assert issues == [{"server": "x", "code": "discovery_failed", "error_type": "TimeoutError"}]

    async def registry_for(self, server, name, schema, result):
        registry = Registry()
        transport = FakeTransport({server: [{"name": name, "inputSchema": schema}]}, {(server, name): result})
        await mcp_client.discover_mcp_tools(registry, transport, [server])
        return registry.get(name), transport

    async def test_logistics_uses_tracking_number_and_formats(self):
        tool, transport = await self.registry_for(
            "logistics", "query_logistics", REMOTE_SCHEMA, {"status_code": "IN_TRANSIT", "secret": "x"},
        )

        assert await tool.invoke({"order_id": "ORD-1001"}, U1, "c1") == {"status_code": "IN_TRANSIT", "status": "运输中"}
        assert transport.calls == [("logistics", "query_logistics", {"tracking_no": "SF-DEMO-1001"})]

    async def test_other_users_order_never_reaches_remote(self):
        tool, transport = await self.registry_for("logistics", "query_logistics", REMOTE_SCHEMA, {})
        result = await tool.invoke({"order_id": "ORD-1002"}, U1, "c1")
        assert result["code"] == "order_not_owned"
        assert transport.calls == []

    async def test_aftersales_passes_order_id(self):
        tool, transport = await self.registry_for(
            "aftersales", "query_warranty", ORDER_SCHEMA, {"warranty": "有效"},
        )
        assert await tool.invoke({"order_id": "ORD-1001"}, U1, "c1") == {"warranty": "有效"}
        assert transport.calls[0][2] == {"order_id": "ORD-1001"}

    async def test_remote_error_result_returned_as_is(self):
        tool, _ = await self.registry_for("logistics", "query_logistics", REMOTE_SCHEMA, {"error": "查无此单"})
        assert await tool.invoke({"order_id": "ORD-1001"}, U1, "c1") == {"error": "查无此单"}

    async def test_malformed_logistics_result(self):
        tool, _ = await self.registry_for("logistics", "query_logistics", REMOTE_SCHEMA, {"status_code": ""})
        with pytest.raises(engine.ToolResultFormatError):
            await tool.invoke({"order_id": "ORD-1001"}, U1, "c1")


class TestStreamableHTTPTransport:
    def test_unknown_server(self):
        with pytest.raises(ValueError, match="未配置"):
            mcp_client.StreamableHTTPTransport({})._url("x")

    @pytest.fixture
    def transport(self, monkeypatch):
        transport = mcp_client.StreamableHTTPTransport({"s": "http://mcp.invalid"})
        state = {}

        class Client:
            async def list_tools(self, cursor=None):
                pages = state["pages"]
                return pages[cursor]

            async def call_tool(self, name, arguments):
                state["called"] = (name, arguments)
                return state["result"]

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_client(server):
            transport._url(server)
            yield Client()

        monkeypatch.setattr(transport, "_client", fake_client)
        return transport, state

    async def test_list_tools_follows_pagination(self, transport):
        transport, state = transport
        tool = lambda name: SimpleNamespace(name=name, description=None, input_schema={"type": "object"})  # noqa: E731
        state["pages"] = {
            None: SimpleNamespace(tools=[tool("a")], next_cursor="p2"),
            "p2": SimpleNamespace(tools=[tool("b")], next_cursor=None),
        }
        assert await transport.list_tools("s") == [
            {"name": "a", "description": "", "inputSchema": {"type": "object"}},
            {"name": "b", "description": "", "inputSchema": {"type": "object"}},
        ]

    @pytest.mark.parametrize(
        "result,expected",
        [
            (SimpleNamespace(is_error=False, structured_content={"ok": 1}, content=[]), {"ok": 1}),
            (SimpleNamespace(is_error=False, structured_content=None,
                             content=[TextContent(type="text", text='{"ok": 2}')]), {"ok": 2}),
            (SimpleNamespace(is_error=False, structured_content=None,
                             content=[TextContent(type="text", text="plain")]),
             {"content": [{"type": "text", "text": "plain"}]}),
        ],
    )
    async def test_call_tool_results(self, transport, result, expected):
        transport, state = transport
        state["result"] = result
        assert await transport.call_tool("s", "t", {"a": 1}) == expected
        assert state["called"] == ("t", {"a": 1})

    @pytest.mark.parametrize(
        "result,error",
        [
            (SimpleNamespace(is_error=True, structured_content=None, content=[]), engine.BusinessError),
            (SimpleNamespace(is_error=False, structured_content=[1], content=[]), engine.ToolResultFormatError),
            (SimpleNamespace(is_error=False, structured_content=None,
                             content=[TextContent(type="text", text="[1]")]), engine.ToolResultFormatError),
            (SimpleNamespace(is_error=False, structured_content=None, content=[]), engine.ToolResultFormatError),
        ],
    )
    async def test_call_tool_errors(self, transport, result, error):
        transport, state = transport
        state["result"] = result
        with pytest.raises(error):
            await transport.call_tool("s", "t", {})


class TestTransportErrorMapping:
    @pytest.fixture
    def failing_client(self, monkeypatch):
        import httpx2

        def install(error):
            class Client:
                def __init__(self, url):
                    self.url = url

                async def __aenter__(self):
                    raise error

                async def __aexit__(self, *exc):
                    return False

            monkeypatch.setattr(mcp_client, "Client", Client)
            return mcp_client.StreamableHTTPTransport({"s": "http://mcp.invalid"})

        return install, httpx2

    @pytest.mark.parametrize(
        "make_error,expected",
        [
            (lambda h: h.ConnectTimeout("t"), TimeoutError),
            (lambda h: h.ConnectError("c"), ConnectionError),
            (lambda h: ExceptionGroup("g", [h.ReadTimeout("t")]), TimeoutError),
            (lambda h: ExceptionGroup("g", [h.ReadError("r"), h.ConnectTimeout("t")]), ConnectionError),
            (lambda h: ExceptionGroup("g", [KeyError("k")]), ExceptionGroup),
        ],
    )
    async def test_maps_transport_errors(self, failing_client, make_error, expected):
        install, httpx2 = failing_client
        transport = install(make_error(httpx2))
        with pytest.raises(expected):
            await transport.list_tools("s")
