"""工具审计的数据结构与安全写入边界。"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from app.tools.context import ToolContext
from app.tools.registry import ToolSpec

if TYPE_CHECKING:
    from app.tools.engine import ToolRun

logger = logging.getLogger(__name__)

AUDIT_ARGUMENT_FIELDS = frozenset({
    "order_id",
    "ticket_type",
    "description",
    "tracking_no",
})


@dataclass(frozen=True, slots=True)
class ToolAuditRecord:
    tool_call_id: str
    conversation_id: str
    tool_name: str

    source: Literal["builtin", "mcp", "unknown"]
    server: str | None

    status: str
    duration_ms: int
    retry_count: int

    argument_fields: tuple[str, ...]
    result_chars: int

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    audit_key: str | None = None

AuditSink = Callable[[ToolAuditRecord], Awaitable[None]]


def build_tool_audit(
    call: object,
    context: ToolContext,
    run: "ToolRun",
    spec: ToolSpec | None,
) -> ToolAuditRecord:
    """从服务端上下文和最终结果构造审计，不保存参数值或结果正文。"""
    args = call.get("args") if isinstance(call, dict) else None
    argument_fields = (
        tuple(sorted(
            field
            for field in args
            if isinstance(field, str)
            and field in AUDIT_ARGUMENT_FIELDS
        ))
        if isinstance(args, dict)
        else ()
    )
    source = spec.source if spec is not None else "unknown"
    server = spec.server if spec is not None else None

    return ToolAuditRecord(
        tool_call_id=run.tool_call_id[:100],
        conversation_id=context.conversation_id[:64],
        tool_name=run.name[:128],
        source=source,
        server=server[:64] if server is not None else None,
        status=run.status[:32],
        duration_ms=run.duration_ms,
        retry_count=run.retry_count,
        argument_fields=argument_fields,
        result_chars=len(run.content),
    )


def build_ticket_decision_audit(
    tool_call: dict,
    conversation_id: int,
    result: dict,
    duration_ms: int,
) -> ToolAuditRecord:
    confirmed = result.get("confirmed")
    if type(confirmed) is not bool:
        raise ValueError("工单决定缺少布尔 confirmed")

    args = tool_call.get("args")
    argument_fields = (
        tuple(sorted(
            key for key in args
            if isinstance(key, str) and key in AUDIT_ARGUMENT_FIELDS
        ))
        if isinstance(args, dict)
        else ()
    )
    call_id = str(tool_call["id"])

    return ToolAuditRecord(
        tool_call_id=call_id[:100],
        conversation_id=str(conversation_id)[:64],
        tool_name="create_ticket",
        source="builtin",
        server=None,
        status="success" if confirmed else "permission_denied",
        duration_ms=duration_ms,
        retry_count=0,
        argument_fields=argument_fields,
        result_chars=len(json.dumps(
            result, ensure_ascii=False, allow_nan=False,
        )),
        audit_key=f"ticket-decision:{conversation_id}:{call_id}",
    )


async def emit_tool_audit(
    sink: AuditSink | None,
    record: ToolAuditRecord,
) -> None:
    """有界写入审计；普通写入失败不改变已经形成的业务结果。"""
    if sink is None:
        return

    try:
        await asyncio.wait_for(
            sink(record),
            timeout=1.0,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning(
            "工具审计写入失败：source=%s status=%s error_type=%s",
            record.source,
            record.status,
            type(error).__name__,
        )
