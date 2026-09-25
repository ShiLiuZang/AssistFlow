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
    """处理器明确报告业务条件不满足。"""
class ToolResultFormatError(Exception):
    """工具返回了不符合本项目结果约定的数据。"""

@dataclass(frozen=True)
class ToolRun:
    tool_call_id: str
    name: str
    status: str
    content: str
    data: dict
    duration_ms: int
    retry_count: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "success"


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
    """按当前工具结果约定分类，供执行和历史恢复共同使用。"""
    if not isinstance(data, dict):
        return "format_error"

    code = data.get("code")

    if code is not None and not isinstance(code, str):
        return "format_error"

    if code == "order_not_owned":
        return "business_error"

    if code in ERROR_STATUSES:
        return code

    if (
        data.get("cancelled") is True
        or data.get("confirmed") is False
    ):
        return "permission_denied"

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
    """将业务结果或安全错误转换成统一结果。"""
    if status == "success":
        status = classify_tool_result(data)
    try:
        content = json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
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
    """检查调用形状、工具是否存在及参数 Schema，不执行工具。"""
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
    spec = registry.get(call["name"])
    if spec is None:
        return None, {
            "code": "unknown_tool",
            "error": "未知工具",
        }
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
    """执行一次受控工具调用；只读暂态故障可有限重试。"""
    started = time.monotonic()
    retry_count = 0

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
        elapsed = int((time.monotonic() - started) * 1000)

        run = make_tool_run(
            safe_call,
            status,
            data,
            duration_ms=elapsed,
            retry_count=retry_count,
        )

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

    spec, error = check_tool_call(call, registry)
    if error is not None:
        return await finish(error["code"], error)

    if spec.permission == "write":
        return await finish(
            "permission_denied",
            {
                "code": "permission_denied",
                "error": "写操作必须通过服务端确认入口处理",
            },
        )

    retry_limit = spec.max_retries if spec.permission == "read" else 0

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
            raise
        except (TimeoutError, ConnectionError) as error:
            status = (
                "timeout"
                if isinstance(error, TimeoutError)
                else "transport_error"
            )

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

            retry_count += 1
            delay = min(
                0.1 * (2 ** min(retry_count - 1, 4)),
                1.0,
            )
            await asyncio.sleep(delay)
        except ToolResultFormatError:
            return await finish(
                "format_error",
                {
                    "code": "format_error",
                    "error": "工具返回结果格式异常，暂时无法确认结果",
                },
            )
        except BusinessError:
            return await finish(
                "business_error",
                {
                    "code": "business_error",
                    "error": "业务条件不满足",
                },
            )
        except Exception:
            return await finish(
                "execution_error",
                {
                    "code": "execution_error",
                    "error": "工具执行失败，请稍后重试",
                },
            )
        else:
            break

    if not isinstance(result, dict):
        return await finish(
            "format_error",
            {
                "code": "format_error",
                "error": "工具已执行，但返回结果格式不符合约定",
            },
        )

    return await finish("success", result)
