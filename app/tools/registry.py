"""
工具注册表模块

本模块提供统一的工具注册、管理和校验机制。
工具注册表负责：
1. 工具规范（ToolSpec）的定义和校验
2. 工具的注册和查询
3. 工具参数的 JSON Schema 校验
4. 为 LLM 生成工具描述（OpenAI 工具格式）
5. 管理本地工具和 MCP 工具

工具分类：
- 本地工具（builtin）：在应用内实现，如订单查询、工单创建
- MCP 工具（mcp）：通过 MCP 协议集成的外部工具，如物流查询、售后系统
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
import math

from jsonschema import Draft202012Validator
from referencing import Registry as RefRegistry
from typing import Literal


@dataclass(frozen=True)
class ToolSpec:
    """
    工具规范

    定义工具的完整元信息和配置。
    使用 frozen=True 确保不可变性（注册后不能修改）。

    属性：
        name: 工具名称（唯一标识）
        invoke: 工具执行函数（接受 args、context、call_id）
        description: 工具描述（供 LLM 理解工具用途）
        schema: 参数 JSON Schema（定义工具参数格式）
        permission: 权限级别
            - "read": 只读操作（如查询订单），无需用户确认
            - "write": 写操作（如创建工单），需要用户确认
        timeout: 超时时间（秒），超时后取消执行
        max_retries: 最大重试次数（仅适用于只读工具）
        source: 工具来源
            - "builtin": 本地工具
            - "mcp": MCP 工具
        server: MCP 服务器名称（仅 MCP 工具需要）
    """
    name: str
    invoke: Callable
    description: str
    schema: dict
    permission: Literal["read", "write"] = "read"
    timeout: float = 5.0
    max_retries: int = 0
    source: Literal["builtin", "mcp"] = "builtin"
    server: str | None = None


class Registry:
    """
    工具注册表

    管理所有可用工具的注册、查询和校验。
    支持本地工具和 MCP 工具的统一管理。
    """

    def __init__(self) -> None:
        """初始化空注册表"""
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """
        注册工具

        对工具规范进行严格校验，确保：
        1. 工具名称唯一且非空
        2. JSON Schema 合法
        3. 参数 Schema 禁止额外字段（additionalProperties: false）
        4. 权限级别正确
        5. 超时和重试配置合理
        6. 来源和服务器配置一致

        Args:
            spec: 工具规范

        Raises:
            ValueError: 如果工具规范不合法
        """
        # 校验 JSON Schema 本身是否合法
        Draft202012Validator.check_schema(spec.schema)

        # 校验工具名称
        if not spec.name.strip():
            raise ValueError("工具名称不能为空")
        if spec.name in self._specs:
            raise ValueError(f"工具已注册：{spec.name}")

        # 校验工具描述
        if not spec.description.strip():
            raise ValueError("工具的描述不能为空")

        # 校验参数 Schema
        if not isinstance(spec.schema, dict) or spec.schema.get("type") != "object":
            raise ValueError("工具参数 Schema 必须是对象")

        # 强制禁止额外字段（防止 LLM 生成无效参数）
        if spec.schema.get("additionalProperties") is not False:
            raise ValueError("工具参数 Schema 必须禁止额外字段")

        # 校验权限级别
        if spec.permission not in {"read", "write"}:
            raise ValueError("工具权限必须是 read 或 write")

        # 校验超时配置（必须是有限的正数）
        if (
            isinstance(spec.timeout, bool)  # 防止 True/False 被识别为 1/0
            or not isinstance(spec.timeout, (int, float))
            or not math.isfinite(spec.timeout)
            or spec.timeout <= 0
        ):
            raise ValueError("工具 timeout 必须是有限的正数")

        # 校验重试次数（必须是非负整数）
        if type(spec.max_retries) is not int or spec.max_retries < 0:
            raise ValueError("工具 max_retries 必须是非负整数")

        # 校验工具来源
        if spec.source not in {"builtin", "mcp"}:
            raise ValueError("工具来源必须是 builtin 或 mcp")

        # 校验来源和服务器配置的一致性
        if spec.source == "builtin" and spec.server is not None:
            raise ValueError("内置工具不能设置 MCP 服务名")

        if spec.source == "mcp":
            if not isinstance(spec.server, str) or not spec.server.strip():
                raise ValueError("MCP 工具必须设置有效的服务名")

        # 深拷贝 schema 防止外部修改
        self._specs[spec.name] = replace(spec, schema=deepcopy(spec.schema))

    def get(self, name: str) -> ToolSpec | None:
        """
        查询工具规范

        Args:
            name: 工具名称

        Returns:
            工具规范，如果不存在返回 None
        """
        return self._specs.get(name)

    def model_tools(self) -> list[dict]:
        """
        生成 LLM 工具描述列表

        将注册的工具转换为 OpenAI 工具格式，供 LLM 调用。

        Returns:
            工具描述列表，格式为：
            [
                {
                    "type": "function",
                    "function": {
                        "name": "tool_name",
                        "description": "tool description",
                        "parameters": { ... }  # JSON Schema
                    }
                },
                ...
            ]
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": deepcopy(spec.schema),  # 深拷贝防止修改
                },
            }
            for spec in self._specs.values()
        ]

    def execution_tools(self) -> dict[str, Callable]:
        """
        生成工具执行函数字典

        Returns:
            工具名称到执行函数的映射
        """
        result = {}
        for name, spec in self._specs.items():
            result[name] = spec.invoke
        return result


def validate_args(spec: ToolSpec, args: object) -> None:
    """
    校验工具参数

    使用 JSON Schema 校验工具调用参数是否符合规范。

    Args:
        spec: 工具规范
        args: 工具参数（通常是字典）

    Raises:
        jsonschema.ValidationError: 如果参数不符合 schema
    """
    Draft202012Validator(
        spec.schema,
        registry=RefRegistry(),  # 空的引用注册表（如需支持 $ref 可扩展）
    ).validate(args)
