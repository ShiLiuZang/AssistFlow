"""
人工坐席工作台接口（坐席或管理员）

- 会话：排队列表、接入/接管、回复与内部备注、转交、结束
- 工单：列表、创建、详情、状态流转
- 实时：GET /api/agent/stream（SSE），推送队列变化与顾客新消息

见 docs/phase2-human-handoff.md。
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core import handoff, tickets
from app.core.auth import Staff, current_staff, require_agent
from app.core import realtime
from app.core.realtime import STAFF

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"], dependencies=[Depends(current_staff), Depends(require_agent)])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class PostIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    kind: Literal["reply", "note"] = "reply"


class TransferIn(BaseModel):
    to: str = Field(min_length=1, max_length=64)


class TicketIn(BaseModel):
    conversation_id: int = Field(ge=1)
    ticket_type: Literal[tickets.TICKET_TYPES] = "咨询"  # type: ignore[valid-type]
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    priority: Literal["普通", "优先"] = "普通"


class TicketStatusIn(BaseModel):
    status: Literal["待处理", "处理中", "已解决", "已关闭"]
    note: str = Field(default="", max_length=1000)


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc) or "不存在")
    if isinstance(exc, handoff.HandoffForbidden):
        return HTTPException(403, str(exc))
    if isinstance(exc, (handoff.HandoffError, tickets.TicketError)):
        return HTTPException(409, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    logger.exception("坐席接口失败")
    return HTTPException(503, "坐席服务暂时不可用")


async def _graph_values(request: Request, conversation_id: int) -> dict | None:
    """主动接管时，用图状态里的证据和订单补全交接卡片；读不到就只用数据库历史。"""
    runtime = getattr(request.app.state, "graph_runtime", None)
    if runtime is None:
        return None
    try:
        owner = await handoff.conversation_owner(conversation_id)
        if owner is None:
            return None
        snapshot = await runtime.graph.aget_state({"configurable": {"thread_id": f"{owner}:{conversation_id}"}})
        return dict(snapshot.values or {})
    except Exception:
        logger.warning("读取图状态失败 conversation_id=%s", conversation_id, exc_info=True)
        return None


# ==================== 会话 ====================

@router.get("/summary")
async def summary(staff: Staff = Depends(current_staff)) -> dict:
    try:
        return {**await handoff.counts(staff.username), "tickets": await tickets.backend.stats()}
    except Exception as exc:
        raise _fail(exc) from exc


@router.get("/conversations")
async def conversations(view: Literal["queued", "mine", "active", "ai", "closed"] = "active",
                        staff: Staff = Depends(current_staff)) -> list[dict]:
    try:
        return await handoff.list_for_staff(view, staff.username)
    except Exception as exc:
        raise _fail(exc) from exc


@router.get("/conversations/{conversation_id}")
async def conversation(conversation_id: int = Path(ge=1)) -> dict:
    try:
        data = await handoff.detail(conversation_id)
        data["tickets"] = await tickets.backend.list(conversation_id=conversation_id, limit=20)
        return data
    except Exception as exc:
        raise _fail(exc) from exc


@router.post("/conversations/{conversation_id}/accept")
async def accept(request: Request, conversation_id: int = Path(ge=1), staff: Staff = Depends(current_staff)) -> dict:
    try:
        return await handoff.accept(conversation_id, staff.username, await _graph_values(request, conversation_id))
    except Exception as exc:
        raise _fail(exc) from exc


@router.post("/conversations/{conversation_id}/messages")
async def post_message(body: PostIn, conversation_id: int = Path(ge=1),
                       staff: Staff = Depends(current_staff)) -> dict:
    try:
        return await handoff.post(conversation_id, staff.username, body.text.strip(), body.kind)
    except Exception as exc:
        raise _fail(exc) from exc


@router.post("/conversations/{conversation_id}/transfer")
async def transfer(body: TransferIn, conversation_id: int = Path(ge=1),
                   staff: Staff = Depends(current_staff)) -> dict:
    try:
        return await handoff.transfer(conversation_id, staff.username, body.to.strip(), is_admin=staff.role == "admin")
    except Exception as exc:
        raise _fail(exc) from exc


@router.post("/conversations/{conversation_id}/close")
async def close(conversation_id: int = Path(ge=1), staff: Staff = Depends(current_staff)) -> dict:
    try:
        return await handoff.close(conversation_id, staff.username, is_admin=staff.role == "admin")
    except Exception as exc:
        raise _fail(exc) from exc


@router.get("/staff")
async def staff_list() -> list[dict]:
    """可转交的坐席账号。"""
    try:
        return await handoff.staff_users()
    except Exception as exc:
        raise _fail(exc) from exc


@router.get("/stream")
async def stream() -> StreamingResponse:
    return StreamingResponse(realtime.hub.stream(STAFF), media_type="text/event-stream", headers=SSE_HEADERS)


# ==================== 工单 ====================

@router.get("/tickets")
async def list_tickets(status: Literal["待处理", "处理中", "已解决", "已关闭"] | None = None,
                       q: str = Query("", max_length=100)) -> list[dict]:
    try:
        return await tickets.backend.list(status=status, q=q)
    except Exception as exc:
        raise _fail(exc) from exc


@router.post("/tickets")
async def create_ticket(body: TicketIn, staff: Staff = Depends(current_staff)) -> dict:
    try:
        owner = await handoff.conversation_owner(body.conversation_id)
        if owner is None:
            raise LookupError("会话不存在")
        ticket = await tickets.backend.create(
            conversation_id=body.conversation_id, user_id=owner, ticket_type=body.ticket_type,
            title=body.title.strip(), description=body.description.strip(), priority=body.priority,
            actor=staff.username, source="staff",
        )
    except Exception as exc:
        raise _fail(exc) from exc
    realtime.hub.publish(STAFF, {"type": "ticket", "ticket_no": ticket["ticket_no"],
                                 "conversation_id": body.conversation_id})
    return ticket


@router.get("/tickets/{ticket_no}")
async def ticket(ticket_no: str = Path(max_length=50)) -> dict:
    try:
        row = await tickets.backend.get(ticket_no)
    except Exception as exc:
        raise _fail(exc) from exc
    if row is None:
        raise HTTPException(404, "工单不存在")
    return row


@router.post("/tickets/{ticket_no}/status")
async def ticket_status(body: TicketStatusIn, ticket_no: str = Path(max_length=50),
                        staff: Staff = Depends(current_staff)) -> dict:
    try:
        row = await tickets.backend.transition(ticket_no, body.status, staff.username, body.note)
    except Exception as exc:
        raise _fail(exc) from exc
    realtime.hub.publish(STAFF, {"type": "ticket", "ticket_no": ticket_no,
                                 "conversation_id": row["conversation_id"]})
    return row
