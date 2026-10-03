"""
工单服务

TicketBackend 是工单系统的接口；LocalTicketBackend 把工单存在本库的 tickets / ticket_events 表。
接入外部工单系统时实现同一接口，再替换 backend 即可，接口层不需要改。

状态流转：
    待处理 → 处理中 / 已关闭
    处理中 → 已解决 / 待处理 / 已关闭
    已解决 → 处理中（重开）/ 已关闭
    已关闭为终态
"""

from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from sqlalchemy import func, or_, select

from app.db import database
from app.db.models import Conversation, Ticket, TicketEvent

STATUSES = ("待处理", "处理中", "已解决", "已关闭")
TRANSITIONS = {
    "待处理": {"处理中", "已关闭"},
    "处理中": {"已解决", "待处理", "已关闭"},
    "已解决": {"处理中", "已关闭"},
    "已关闭": set(),
}
PRIORITIES = ("普通", "优先")
TICKET_TYPES = ("退款", "退货", "换货", "补发", "物流", "投诉", "咨询", "其他")


class TicketError(ValueError):
    """业务规则不允许的操作（接口层转为 409）。"""


def _now() -> datetime:
    # 与数据库 server_default 的 now() 一致，按 UTC 存不带时区的时间（前端按 UTC 解析）
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def ticket_view(row: Ticket, events: list[TicketEvent] | None = None) -> dict:
    data = {
        "ticket_no": row.ticket_no,
        "conversation_id": row.conversation_id,
        "user_id": row.user_id,
        "ticket_type": row.ticket_type,
        "title": row.title or row.description[:30],
        "description": row.description,
        "status": row.status,
        "priority": row.priority or "普通",
        "assignee": row.assignee,
        "source": row.source or "customer",
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at or row.created_at),
    }
    if events is not None:
        data["events"] = [
            {
                "actor": e.actor, "action": e.action, "from_status": e.from_status,
                "to_status": e.to_status, "note": e.note, "created_at": _iso(e.created_at),
            }
            for e in events
        ]
    return data


class TicketBackend(Protocol):
    async def create(self, *, conversation_id: int, user_id: str, ticket_type: str, title: str,
                     description: str, priority: str, actor: str, source: str) -> dict: ...

    async def list(self, *, status: str | None = None, q: str = "", conversation_id: int | None = None,
                   limit: int = 100) -> list[dict]: ...

    async def get(self, ticket_no: str) -> dict | None: ...

    async def transition(self, ticket_no: str, to_status: str, actor: str, note: str = "") -> dict: ...

    async def stats(self) -> dict[str, int]: ...


class LocalTicketBackend:
    async def create(self, *, conversation_id: int, user_id: str, ticket_type: str, title: str,
                     description: str, priority: str = "普通", actor: str, source: str = "staff") -> dict:
        if priority not in PRIORITIES:
            raise TicketError("优先级不正确")
        async with database.SessionLocal() as session, session.begin():
            owner = await session.scalar(select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id))
            if owner is None:
                raise LookupError("会话不存在")
            ticket = Ticket(
                conversation_id=conversation_id, user_id=user_id, ticket_no="PENDING-" + uuid4().hex,
                ticket_type=ticket_type, title=title.strip() or None, description=description,
                priority=priority, source=source, status="待处理", updated_at=_now(),
            )
            session.add(ticket)
            await session.flush()
            ticket.ticket_no = f"T{datetime.now():%Y%m%d}{ticket.id:04d}"
            event = TicketEvent(ticket_id=ticket.id, actor=actor, action="create", to_status="待处理",
                                note="坐席创建" if source == "staff" else "顾客在会话中确认创建")
            session.add(event)
            await session.flush()
            return ticket_view(ticket, [event])

    async def list(self, *, status: str | None = None, q: str = "", conversation_id: int | None = None,
                   limit: int = 100) -> list[dict]:
        statement = select(Ticket).order_by(Ticket.id.desc()).limit(limit)
        if status:
            statement = statement.where(Ticket.status == status)
        if conversation_id is not None:
            statement = statement.where(Ticket.conversation_id == conversation_id)
        if q.strip():
            like = f"%{q.strip()}%"
            statement = statement.where(or_(Ticket.ticket_no.like(like), Ticket.title.like(like),
                                            Ticket.description.like(like), Ticket.user_id.like(like)))
        async with database.SessionLocal() as session:
            return [ticket_view(row) for row in await session.scalars(statement)]

    async def get(self, ticket_no: str) -> dict | None:
        async with database.SessionLocal() as session:
            row = await session.scalar(select(Ticket).where(Ticket.ticket_no == ticket_no))
            if row is None:
                return None
            events = list(await session.scalars(
                select(TicketEvent).where(TicketEvent.ticket_id == row.id).order_by(TicketEvent.id)))
            return ticket_view(row, events)

    async def transition(self, ticket_no: str, to_status: str, actor: str, note: str = "") -> dict:
        if to_status not in STATUSES:
            raise TicketError("工单状态不正确")
        async with database.SessionLocal() as session, session.begin():
            row = await session.scalar(select(Ticket).where(Ticket.ticket_no == ticket_no).with_for_update())
            if row is None:
                raise LookupError("工单不存在")
            current = row.status if row.status in TRANSITIONS else "待处理"
            if to_status == current:
                if not note.strip():
                    raise TicketError(f"工单已是「{current}」")
                action = "note"
            elif to_status not in TRANSITIONS[current]:
                raise TicketError(f"工单不能从「{current}」改为「{to_status}」")
            else:
                action = "status"
                row.status = to_status
                if to_status == "处理中" and not row.assignee:
                    row.assignee = actor
            row.updated_at = _now()
            session.add(TicketEvent(ticket_id=row.id, actor=actor, action=action,
                                    from_status=current if action == "status" else None,
                                    to_status=to_status if action == "status" else None,
                                    note=note.strip() or None))
            await session.flush()
            events = list(await session.scalars(
                select(TicketEvent).where(TicketEvent.ticket_id == row.id).order_by(TicketEvent.id)))
            return ticket_view(row, events)

    async def stats(self) -> dict[str, int]:
        async with database.SessionLocal() as session:
            rows = (await session.execute(select(Ticket.status, func.count()).group_by(Ticket.status))).all()
        result = {status: 0 for status in STATUSES}
        for status, count in rows:
            result[status if status in result else "待处理"] += int(count)
        return result


backend: TicketBackend = LocalTicketBackend()
