# 模块：MCP工具客户端
# 通过MCP协议动态发现和调用远程工具，集成第三方服务能力
# 支持白名单策略、权限校验、参数转换、结果格式化
# 核心职责：桥接MCP服务与本地工具注册表，确保安全可控

import asyncio
import json
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
    """MCP工具定义标准格式"""
    name: str  # 工具名称
    description: str  # 工具描述
    inputSchema: dict[str, Any]  # 参数schema（JSON Schema格式）


class MCPTransport(Protocol):
    """
    MCP传输层协议

    设计说明:
        统一真实MCP SDK和离线fake的接口
        便于测试和多种传输方式扩展
    """

    async def list_tools(self, server: str) -> list[MCPToolDefinition]:
        """
        列出服务器的工具清单

        参数:
            server: 服务器标识

        返回:
            标准化的工具定义列表
        """
        ...

    async def call_tool(
        self,
        server: str,
        name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """
        调用远程工具

        参数:
            server: 服务器标识
            name: 工具名称
            args: 调用参数

        返回:
            标准化的结果对象

        异常:
            传输错误时抛出异常
        """
        ...


# MCP工具白名单：(服务器, 工具名) -> 权限
# 只有列入白名单的工具才能被注册和调用
MCP_POLICY: dict[tuple[str, str], Literal["read"]] = {
    ("logistics", "query_logistics"): "read",
    ("aftersales", "query_warranty"): "read",
    ("aftersales", "query_return_status"): "read",
}

# 订单查询参数schema（本地统一接口）
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
    """
    逐台发现MCP工具并注册到工具注册表

    参数:
        registry: 工具注册表
        transport: MCP传输层实现
        servers: 服务器标识列表
        discovery_timeout: 单台服务器的发现超时（秒）

    返回:
        问题清单列表，每项包含server、code、error_type等字段

    发现流程:
        1. 遍历每台服务器
        2. 调用list_tools获取工具清单
        3. 校验工具名称、权限白名单
        4. 校验参数schema格式
        5. 注册工具到registry

    容错设计:
        单台服务器失败不中断其他服务器的发现
        所有错误记录到issues列表，最后统一返回
        确保部分MCP服务不可用时系统仍可启动

    白名单策略:
        只注册MCP_POLICY中列出的(server, name)组合
        未列入白名单的工具跳过并记录not_allowlisted

    参数转换:
        本地接口统一为order_id参数（ORDER_QUERY_SCHEMA）
        调用MCP工具时转换为远程参数（tracking_no或order_id）

    权限校验:
        工具调用前检查订单归属，只能查询自己的订单
        防止用户通过工具访问他人数据
    """
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

            # 白名单校验
            permission = MCP_POLICY.get((server, name))
            if permission is None:
                issues.append({
                    "server": server,
                    "code": "not_allowlisted",
                    "name": name,
                })
                continue

            # 名称冲突检测
            if registry.get(name) is not None:
                issues.append({
                    "server": server,
                    "code": "name_collision",
                    "name": name,
                })
                continue

            try:
                # 校验远程参数schema
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

                # 工具描述映射
                descriptions = {
                    ("logistics", "query_logistics"):
                        "根据当前用户的订单号查询物流状态。",
                    ("aftersales", "query_warranty"):
                        "根据当前用户的订单号查询保修状态。",
                    ("aftersales", "query_return_status"):
                        "根据当前用户的订单号查询退货状态。",
                }

                # 定义工具调用函数
                async def invoke(
                    args: dict[str, Any],
                    context: ToolContext,
                    _call_id: str,
                    *,
                    server_name: str = server,
                    tool_name: str = name,
                    validator: Draft202012Validator = remote_validator,
                ) -> dict[str, Any]:
                    """
                    工具调用包装函数

                    处理流程:
                        1. 提取order_id，校验订单归属
                        2. 转换参数格式（order_id -> tracking_no或order_id）
                        3. 调用远程MCP工具
                        4. 格式化结果（物流工具特殊处理）

                    权限校验:
                        get_user_order确保只能查询自己的订单
                        订单不存在或不属于当前用户时返回错误

                    参数转换:
                        物流查询：order_id -> tracking_no
                        其他查询：order_id -> order_id（透传）
                    """
                    order_id = args["order_id"]
                    order = get_user_order(order_id, context.user_id)

                    if order is None:
                        return {
                            "found": False,
                            "code": "order_not_owned",
                            "error": "没有找到您的这笔订单",
                        }

                    # 物流查询需要转换为tracking_no
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

                    # 校验远程参数格式
                    validator.validate(remote_args)

                    # 调用MCP工具
                    result = await transport.call_tool(
                        server_name,
                        tool_name,
                        remote_args,
                    )

                    # 检查结果分类
                    if classify_tool_result(result) != "success":
                        return result

                    # 物流结果特殊格式化
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

                # 注册工具到registry
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
    """
    基于官方MCP Python SDK的HTTP传输层实现

    通过Streamable HTTP协议连接受配置管理的MCP服务
    支持工具发现、工具调用、错误分类和重试
    核心职责：封装MCP SDK，提供统一的传输接口
    """

    def __init__(self, server_urls: Mapping[str, str]) -> None:
        """
        初始化传输层

        参数:
            server_urls: 服务器标识 -> URL的映射（如 {"logistics": "http://localhost:8001"}）
        """
        self._server_urls = dict(server_urls)

    def _url(self, server: str) -> str:
        """
        获取服务器URL

        参数:
            server: 服务器标识

        返回:
            服务器URL

        异常:
            ValueError: 服务器未配置
        """
        try:
            return self._server_urls[server]
        except KeyError as error:
            raise ValueError(f"未配置 MCP 服务：{server}") from error

    @asynccontextmanager
    async def _client(self, server: str):
        """
        创建MCP客户端上下文

        参数:
            server: 服务器标识

        返回:
            MCP客户端实例

        异常处理:
            将httpx2的各种传输异常分类为：
            - TimeoutError: 请求超时
            - ConnectionError: 连接或传输失败
            - 其他异常：原样抛出

        设计说明:
            使用ExceptionGroup处理SDK可能抛出的异常组
            区分超时和传输错误，便于上层重试策略
        """
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
            # 处理异常组：分离超时和传输错误
            _, non_timeout = error.split(httpx2.TimeoutException)

            if non_timeout is None:
                raise TimeoutError("MCP 请求超时") from error

            _, non_transport = error.split(retryable_errors)

            if non_transport is None:
                raise ConnectionError("MCP 连接或传输失败") from error

            raise

    async def list_tools(self, server: str) -> list[MCPToolDefinition]:
        """
        列出服务器的工具清单

        参数:
            server: 服务器标识

        返回:
            标准化的工具定义列表

        处理逻辑:
            支持分页，循环获取直到cursor为None
            将MCP SDK的Tool对象转换为标准格式

        设计说明:
            MCP协议支持分页避免单次返回过大
            description可能为空，统一转为空字符串
        """
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
        """
        调用远程工具

        参数:
            server: 服务器标识
            name: 工具名称
            args: 调用参数

        返回:
            标准化的结果对象

        结果格式:
            1. 优先返回structured_content（已结构化的字典）
            2. 否则尝试解析TextContent为JSON对象
            3. 如无法解析，返回{"content": [文本块列表]}

        异常:
            BusinessError: 远端工具执行失败（is_error=True）
            ToolResultFormatError: 结果格式不符合预期

        设计说明:
            MCP协议支持多种结果格式（结构化、文本、嵌入等）
            本实现只处理结构化和文本格式
            文本格式尝试解析为JSON，失败则包装为content块
        """
        async with self._client(server) as client:
            result = await client.call_tool(name, arguments=args)

        if result.is_error:
            raise BusinessError("远端 MCP 工具执行失败")

        # 优先使用结构化内容
        structured = result.structured_content
        if structured is not None:
            if not isinstance(structured, dict):
                raise ToolResultFormatError("远端 MCP 工具结构化结果格式无效")
            return structured

        # 提取文本块
        text_blocks = [
            {"type": "text", "text": block.text}
            for block in result.content
            if isinstance(block, TextContent)
        ]
        if text_blocks:
            text = "\n".join(block["text"] for block in text_blocks)
            try:
                parsed = json.loads(text)
            except ValueError:
                pass
            else:
                if not isinstance(parsed, dict):
                    raise ToolResultFormatError("远端 MCP 工具 JSON 结果必须是对象")
                return parsed
            return {"content": text_blocks}

        raise ToolResultFormatError("远端 MCP 工具没有可处理的结果")
