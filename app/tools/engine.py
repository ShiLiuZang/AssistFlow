"""
工具执行引擎模块

本模块提供统一的工具执行框架，负责：
1. 工具调用的校验（格式、参数、权限）
2. 工具执行（带超时和重试）
3. 结果分类和格式化
4. 审计日志记录

错误分类：
- invalid_call: 调用格式不正确
- unknown_tool: 工具不存在
- invalid_args: 参数不符合 Schema
- permission_denied: 权限不足（写操作需确认）
- business_error: 业务条件不满足（如订单不存在）
- execution_error: 工具执行异常
- format_error: 结果格式不正确
- timeout: 执行超时
- transport_error: 传输错误（网络故障等）

参考 git commit 7a3584a (增加统一工具执行与错误分类)
参考 git commit df3eed9 (为只读工具增加超时与有限重试)
"""

import asyncio
import json
import time
from dataclasses import dataclass

from jsonschema.exceptions import ValidationError

from app.tools.context import ToolContext
from app.tools.registry import Registry, ToolSpec, validate_args
from app.tools.audit import (
    AuditSink,
    build_tool_audit,
    emit_tool_audit,
)


class BusinessError(Exception):
    """
    业务错误异常

    工具处理器明确报告业务条件不满足。
    例如：订单不存在、订单不属于当前用户、退款不可用等。
    """
    pass


class ToolResultFormatError(Exception):
    """
    工具结果格式错误异常

    工具返回了不符合本项目结果约定的数据。
    例如：返回非字典类型、缺少必需字段等。
    """
    pass


@dataclass(frozen=True)
class ToolRun:
    """
    工具执行结果

    封装工具调用的完整执行结果，包括状态、内容、耗时等。

    属性：
        tool_call_id: 工具调用 ID
        name: 工具名称
        status: 执行状态（success 或错误码）
        content: 结果 JSON 字符串（用于 LLM 消息）
        data: 结果字典
        duration_ms: 执行耗时（毫秒）
        retry_count: 重试次数
    """
    tool_call_id: str
    name: str
    status: str
    content: str
    data: dict
    duration_ms: int
    retry_count: int = 0

    @property
    def ok(self) -> bool:
        """判断执行是否成功"""
        return self.status == "success"


# 所有可能的错误状态码
ERROR_STATUSES = frozenset({
    "invalid_call",
    "unknown_tool",
    "invalid_args",
    "invalid_schema",
    "permission_denied",
    "business_error",
    "execution_error",
    "format_error",
    "timeout",
    "transport_error",
})


def classify_tool_result(data: object) -> str:
    """
    按当前工具结果约定分类

    根据结果数据判断执行状态，供执行和历史恢复共同使用。

    Args:
        data: 工具返回的结果数据

    Returns:
        状态码：success 或错误码

    分类规则：
    1. 如果有 code 字段且在 ERROR_STATUSES 中，返回该 code
    2. 如果 code 为 "order_not_owned"，返回 business_error
    3. 如果 cancelled=True 或 confirmed=False，返回 permission_denied
    4. 如果有 error 字段，返回 business_error
    5. 否则返回 success

    参考 git commit 66b5981 (修复工具调用重复标识与结果状态恢复)
    """
    if not isinstance(data, dict):
        return "format_error"

    code = data.get("code")

    if code is not None and not isinstance(code, str):
        return "format_error"

    # 特定业务错误码
    if code == "order_not_owned":
        return "business_error"

    # 系统错误码
    if code in ERROR_STATUSES:
        return code

    # 用户取消或确认失败
    if (
        data.get("cancelled") is True
        or data.get("confirmed") is False
    ):
        return "permission_denied"

    # 通用错误字段
    if data.get("error"):
        return "business_error"

    return "success"


def make_tool_run(
    call: dict,
    status: str,
    data: dict,
    *,
    duration_ms: int = 0,
    retry_count: int = 0,
) -> ToolRun:
    """
    将业务结果或安全错误转换成统一结果

    Args:
        call: 工具调用对象
        status: 初始状态（"success" 会被重新分类）
        data: 结果数据
        duration_ms: 执行耗时
        retry_count: 重试次数

    Returns:
        标准化的 ToolRun 对象

    处理逻辑：
    1. 如果 status 为 "success"，重新分类结果
    2. 将 data 序列化为 JSON 字符串
    3. 如果序列化失败，返回 format_error
    """
    # 成功状态需要重新分类（可能是业务错误）
    if status == "success":
        status = classify_tool_result(data)

    # 尝试序列化结果
    try:
        content = json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        # 序列化失败，返回格式错误
        status = "format_error"
        data = {
            "code": "format_error",
            "error": "工具已执行，但结果无法序列化，请核对业务状态",
        }
        content = json.dumps(data, ensure_ascii=False)

    return ToolRun(
        tool_call_id=call.get("id", ""),
        name=call.get("name", ""),
        status=status,
        content=content,
        data=data,
        duration_ms=duration_ms,
        retry_count=retry_count,
    )


def check_tool_call(
    call: object,
    registry: Registry,
) -> tuple[ToolSpec | None, dict[str, str] | None]:
    """
    检查调用形状、工具是否存在及参数 Schema

    不执行工具，仅进行静态校验。

    Args:
        call: 工具调用对象
        registry: 工具注册表

    Returns:
        (工具规范, 错误信息)
        - 如果校验通过：(ToolSpec, None)
        - 如果校验失败：(None 或 ToolSpec, 错误字典)

    校验步骤：
    1. 检查调用格式（id、name、args）
    2. 检查工具是否存在
    3. 校验参数是否符合 Schema

    参考 git commit 7d21aac (增加工具参数统一校验)
    """
    # 1. 检查调用格式
    if (
        not isinstance(call, dict)
        or not isinstance(call.get("id"), str)
        or not call["id"].strip()
        or not isinstance(call.get("name"), str)
        or not call["name"].strip()
        or not isinstance(call.get("args"), dict)
    ):
        return None, {
            "code": "invalid_call",
            "error": "工具调用必须包含有效的 id、name 和对象 args",
        }

    # 2. 检查工具是否存在
    spec = registry.get(call["name"])
    if spec is None:
        return None, {
            "code": "unknown_tool",
            "error": "未知工具",
        }

    # 3. 校验参数 Schema
    try:
        validate_args(spec, call["args"])
    except ValidationError:
        return spec, {
            "code": "invalid_args",
            "error": "工具参数不符合 Schema，请补充后重试",
        }
    except Exception:
        return spec, {
            "code": "invalid_schema",
            "error": "工具参数定义异常",
        }

    return spec, None


async def execute_tool_call(
    call: object,
    context: ToolContext,
    registry: Registry,
    *,
    audit_sink: AuditSink | None = None,
) -> ToolRun:
    """
    执行一次受控工具调用

    只读暂态故障可有限重试。

    Args:
        call: 工具调用对象
        context: 工具上下文（包含 user_id 等）
        registry: 工具注册表
        audit_sink: 审计回调（可选）

    Returns:
        工具执行结果

    执行流程：
    1. 校验工具调用格式和参数
    2. 检查权限（写操作必须通过确认流程）
    3. 执行工具（带超时和重试）
    4. 记录审计日志

    重试策略：
    - 仅只读工具支持重试
    - 仅 TimeoutError 和 ConnectionError 触发重试
    - 指数退避：0.1s, 0.2s, 0.4s, 0.8s, 1.0s
    - 最大重试次数由 spec.max_retries 决定

    参考 git commit df3eed9 (为只读工具增加超时与有限重试)
    参考 git commit ded9aed (完成工具结果格式化与审计落库)
    """
    started = time.monotonic()
    retry_count = 0

    # 提取安全的调用标识（防止后续代码访问非法字段）
    safe_call = {
        "id": (
            call.get("id", "")
            if isinstance(call, dict)
            and isinstance(call.get("id"), str)
            else ""
        ),
        "name": (
            call.get("name", "")
            if isinstance(call, dict)
            and isinstance(call.get("name"), str)
            else ""
        ),
    }

    async def finish(status: str, data: dict) -> ToolRun:
        """
        结束工具执行并记录审计

        Args:
            status: 执行状态
            data: 结果数据

        Returns:
            工具执行结果
        """
        elapsed = int((time.monotonic() - started) * 1000)

        run = make_tool_run(
            safe_call,
            status,
            data,
            duration_ms=elapsed,
            retry_count=retry_count,
        )

        # 记录审计日志
        if audit_sink is not None:
            registered_spec = registry.get(safe_call["name"])

            record = build_tool_audit(
                call,
                context,
                run,
                registered_spec,
            )
            await emit_tool_audit(audit_sink, record)

        return run

    # 1. 校验工具调用
    spec, error = check_tool_call(call, registry)
    if error is not None:
        return await finish(error["code"], error)

    # 2. 检查权限（写操作必须通过确认流程）
    if spec.permission == "write":
        return await finish(
            "permission_denied",
            {
                "code": "permission_denied",
                "error": "写操作必须通过服务端确认入口处理",
            },
        )

    # 3. 确定重试限制（只读工具才支持重试）
    retry_limit = spec.max_retries if spec.permission == "read" else 0

    # 4. 执行工具（带重试）
    while True:
        try:
            result = await asyncio.wait_for(
                spec.invoke(
                    dict(call["args"]),
                    context,
                    call["id"],
                ),
                timeout=spec.timeout,
            )
        except asyncio.CancelledError:
            # 不捕获取消异常（让上层处理）
            raise
        except (TimeoutError, ConnectionError) as error:
            # 超时或连接错误：可重试
            status = (
                "timeout"
                if isinstance(error, TimeoutError)
                else "transport_error"
            )

            # 检查是否已达重试限制
            if retry_count >= retry_limit:
                if status == "timeout":
                    message = "查询超时，暂时无法确认结果"
                else:
                    message = "连接暂时不可用，请稍后再试"

                return await finish(
                    status,
                    {
                        "code": status,
                        "error": message,
                    },
                )

            # 指数退避重试
            retry_count += 1
            delay = min(
                0.1 * (2 ** min(retry_count - 1, 4)),  # 最大 1.6s，但限制为 1.0s
                1.0,
            )
            await asyncio.sleep(delay)
        except ToolResultFormatError:
            # 工具返回格式错误
            return await finish(
                "format_error",
                {
                    "code": "format_error",
                    "error": "工具返回结果格式异常，暂时无法确认结果",
                },
            )
        except BusinessError:
            # 业务错误
            return await finish(
                "business_error",
                {
                    "code": "business_error",
                    "error": "业务条件不满足",
                },
            )
        except Exception:
            # 其他执行错误
            return await finish(
                "execution_error",
                {
                    "code": "execution_error",
                    "error": "工具执行失败，请稍后重试",
                },
            )
        else:
            # 执行成功，跳出重试循环
            break

    # 5. 校验结果格式
    if not isinstance(result, dict):
        return await finish(
            "format_error",
            {
                "code": "format_error",
                "error": "工具已执行，但返回结果格式不符合约定",
            },
        )

    return await finish("success", result)
