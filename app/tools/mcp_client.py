import asyncio
from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any, Literal, Protocol, TypedDict

from mcp import Client
from mcp.types import TextContent

import httpx2
from jsonschema import Draft202012Validator
from referencing import Registry as RefRegistry

from app.tools.engine import (
    BusinessError,
    ToolResultFormatError,
    classify_tool_result,
)
from app.tools.formatting import format_logistics_result
from app.tools.orders import get_user_order, get_user_tracking_no
from app.tools.context import ToolContext
from app.tools.registry import Registry, ToolSpec


class MCPToolDefinition(TypedDict):
    name: str
    description: str
    inputSchema: dict[str, Any]


class MCPTransport(Protocol):
    """将真实 MCP SDK 或离线 fake 统一到这个传输接口。"""

    async def list_tools(self, server: str) -> list[MCPToolDefinition]:
        """返回标准化后的工具定义列表。"""
        ...

    async def call_tool(
        self,
        server: str,
        name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """返回标准化后的对象；传输错误应抛出异常。"""
        ...


MCP_POLICY: dict[tuple[str, str], Literal["read"]] = {
    ("logistics", "query_logistics"): "read",
    ("aftersales", "query_warranty"): "read",
    ("aftersales", "query_return_status"): "read",
}
ORDER_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "order_id": {
            "type": "string",
            "minLength": 1,
            "description": "当前用户需要查询的订单号，例如 ORD-1001",
        },
    },
    "required": ["order_id"],
    "additionalProperties": False,
}

async def discover_mcp_tools(
    registry: Registry,
    transport: MCPTransport,
    servers: Sequence[str],
    *,
    discovery_timeout: float = 1.0,
) -> list[dict[str, str]]:
    """逐台发现 MCP 工具；返回问题清单，不让单台故障中断其他服务。"""
    issues: list[dict[str, str]] = []

    for server in servers:
        try:
            tools = await asyncio.wait_for(
                transport.list_tools(server),
                timeout=discovery_timeout,
            )
        except Exception as error:
            issues.append({
                "server": server,
                "code": "discovery_failed",
                "error_type": type(error).__name__,
            })
            continue

        if not isinstance(tools, list):
            issues.append({
                "server": server,
                "code": "invalid_catalog",
                "error_type": "TypeError",
            })
            continue

        for item in tools:
            name = item.get("name") if isinstance(item, dict) else None

            if not isinstance(name, str) or not name:
                issues.append({
                    "server": server,
                    "code": "registration_failed",
                    "error_type": "InvalidToolName",
                })
                continue

            permission = MCP_POLICY.get((server, name))
            if permission is None:
                issues.append({
                    "server": server,
                    "code": "not_allowlisted",
                    "name": name,
                })
                continue

            if registry.get(name) is not None:
                issues.append({
                    "server": server,
                    "code": "name_collision",
                    "name": name,
                })
                continue

            try:
                remote_schema = deepcopy(item["inputSchema"])
                Draft202012Validator.check_schema(remote_schema)

                if (
                    not isinstance(remote_schema, dict)
                    or remote_schema.get("type") != "object"
                ):
                    raise ValueError("远端工具参数必须是对象")

                remote_validator = Draft202012Validator(
                    remote_schema,
                    registry=RefRegistry(),
                )

                descriptions = {
                    ("logistics", "query_logistics"):
                        "根据当前用户的订单号查询物流状态。",
                    ("aftersales", "query_warranty"):
                        "根据当前用户的订单号查询保修状态。",
                    ("aftersales", "query_return_status"):
                        "根据当前用户的订单号查询退货状态。",
                }

                async def invoke(
                    args: dict[str, Any],
                    context: ToolContext,
                    _call_id: str,
                    *,
                    server_name: str = server,
                    tool_name: str = name,
                    validator: Draft202012Validator = remote_validator,
                ) -> dict[str, Any]:
                    order_id = args["order_id"]
                    order = get_user_order(order_id, context.user_id)

                    if order is None:
                        return {
                            "found": False,
                            "code": "order_not_owned",
                            "error": "没有找到您的这笔订单",
                        }

                    if (server_name, tool_name) == (
                        "logistics",
                        "query_logistics",
                    ):
                        tracking_no = get_user_tracking_no(
                            order_id,
                            context.user_id,
                        )

                        if not tracking_no:
                            raise BusinessError("该订单暂无可查询的物流号")

                        remote_args = {"tracking_no": tracking_no}
                    else:
                        remote_args = {"order_id": order["order_id"]}

                    validator.validate(remote_args)

                    result = await transport.call_tool(
                        server_name,
                        tool_name,
                        remote_args,
                    )

                    if classify_tool_result(result) != "success":
                        return result

                    if (server_name, tool_name) == (
                        "logistics",
                        "query_logistics",
                    ):
                        try:
                            return format_logistics_result(result)
                        except ValueError as error:
                            raise ToolResultFormatError(
                                "物流结果格式不符合约定"
                            ) from error

                    return result

                registry.register(ToolSpec(
                    name=name,
                    invoke=invoke,
                    description=descriptions[(server, name)],
                    schema=deepcopy(ORDER_QUERY_SCHEMA),
                    permission=permission,
                    timeout=5.0,
                    max_retries=2,
                    source="mcp",
                    server=server,
                ))
            except Exception as error:
                issues.append({
                    "server": server,
                    "code": "registration_failed",
                    "name": name,
                    "error_type": type(error).__name__,
                })

    return issues


class StreamableHTTPTransport:
    """通过官方 MCP Python SDK 连接受配置管理的 Streamable HTTP 服务。"""

    def __init__(self, server_urls: Mapping[str, str]) -> None:
        self._server_urls = dict(server_urls)

    def _url(self, server: str) -> str:
        try:
            return self._server_urls[server]
        except KeyError as error:
            raise ValueError(f"未配置 MCP 服务：{server}") from error

    @asynccontextmanager
    async def _client(self, server: str):
        retryable_errors = (
            httpx2.TimeoutException,
            httpx2.ConnectError,
            httpx2.ReadError,
            httpx2.WriteError,
        )

        try:
            async with Client(self._url(server)) as client:
                yield client
        except httpx2.TimeoutException as error:
            raise TimeoutError("MCP 请求超时") from error
        except (
            httpx2.ConnectError,
            httpx2.ReadError,
            httpx2.WriteError,
        ) as error:
            raise ConnectionError("MCP 连接或传输失败") from error
        except ExceptionGroup as error:
            _, non_timeout = error.split(httpx2.TimeoutException)

            if non_timeout is None:
                raise TimeoutError("MCP 请求超时") from error

            _, non_transport = error.split(retryable_errors)

            if non_transport is None:
                raise ConnectionError("MCP 连接或传输失败") from error

            raise

    async def list_tools(self, server: str) -> list[MCPToolDefinition]:
        async with self._client(server) as client:
            discovered = []
            cursor = None

            while True:
                page = await client.list_tools(cursor=cursor)
                discovered.extend(page.tools)
                cursor = page.next_cursor

                if cursor is None:
                    break

        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.input_schema,
            }
            for tool in discovered
        ]

    async def call_tool(
        self,
        server: str,
        name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._client(server) as client:
            result = await client.call_tool(name, arguments=args)

        if result.is_error:
            raise BusinessError("远端 MCP 工具执行失败")

        structured = result.structured_content
        if structured is not None:
            if not isinstance(structured, dict):
                raise ToolResultFormatError("远端 MCP 工具结构化结果格式无效")
            return structured

        text_blocks = [
            {"type": "text", "text": block.text}
            for block in result.content
            if isinstance(block, TextContent)
        ]
        if text_blocks:
            return {"content": text_blocks}

        raise ToolResultFormatError("远端 MCP 工具没有可处理的结果")
