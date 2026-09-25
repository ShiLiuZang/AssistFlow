import asyncio
import json
import time
from dataclasses import dataclass

from jsonschema.exceptions import ValidationError

from app.tools.context import ToolContext
from app.tools.registry import Registry, ToolSpec, validate_args


class BusinessError(Exception):
    """处理器明确报告业务条件不满足。"""


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


def make_tool_run(
    call: dict,
    status: str,
    data: dict,
    *,
    duration_ms: int = 0,
) -> ToolRun:
    """将业务结果或安全错误转换成统一结果。"""
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
)-> ToolRun:
    """执行一次只读工具调用，返回统一结果；取消向上传播。"""
    started = time.monotonic()
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

    def finish(status: str, data: dict) -> ToolRun:
        elapsed = int((time.monotonic() - started) * 1000)
        return make_tool_run(
            safe_call,
            status,
            data,
            duration_ms=elapsed,
        )

    spec, error = check_tool_call(call, registry)
    if error is not None:
        return finish(error["code"], error)

    if spec.permission == "write":
        return finish(
            "permission_denied",
            {
                "code": "permission_denied",
                "error": "写操作必须通过服务端确认入口处理",
            },
        )

    try:
        result = await spec.invoke(
            dict(call["args"]),
            context,
            call["id"],
        )
    except asyncio.CancelledError:
        raise
    except BusinessError:
        return finish(
            "business_error",
            {
                "code": "business_error",
                "error": "业务条件不满足",
            },
        )
    except Exception:
        return finish(
            "execution_error",
            {
                "code": "execution_error",
                "error": "工具执行失败，请稍后重试",
            },
        )

    if not isinstance(result, dict):
        return finish(
            "format_error",
            {
                "code": "format_error",
                "error": "工具已执行，但返回结果格式不符合约定",
            },
        )

    if (
            call["name"] == "query_order"
            and result.get("found") is False
            and result.get("code") == "order_not_owned"
    ):
        return finish("business_error", result)

    return finish("success", result)
