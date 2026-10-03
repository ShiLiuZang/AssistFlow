"""
渠道数据：买家会话映射、收发记录、订单归属

时间按 UTC 存不带时区的值，与其他表一致。收发记录的 created_at 由这里写入，
不依赖数据库时区（补处理和统计按它取最近的记录）。
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.db.models import ChannelMessage, ChannelOrder, ChannelSession, Conversation, Handoff

logger = logging.getLogger(__name__)

OPEN_HANDOFF = ("queued", "active")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _session_view(row: ChannelSession) -> dict:
    return {"session_id": row.id, "channel": row.channel, "shop_id": row.shop_id, "buyer_id": row.buyer_id,
            "user_id": row.user_id, "conversation_id": row.conversation_id}


async def get_or_create_session(channel: str, shop_id: str, buyer_id: str, user_prefix: str) -> dict:
    """买家第一次来时分配内部顾客 ID（随机，不由平台 ID 推出）。"""
    statement = select(ChannelSession).where(ChannelSession.channel == channel, ChannelSession.shop_id == shop_id,
                                             ChannelSession.buyer_id == buyer_id)
    async with database.SessionLocal() as session:
        row = await session.scalar(statement)
        if row is not None:
            return _session_view(row)
        row = ChannelSession(channel=channel, shop_id=shop_id, buyer_id=buyer_id,
                             user_id=user_prefix + uuid4().hex[:24])
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:  # 同一买家的两条消息同时到达
            await session.rollback()
            row = await session.scalar(statement)
        return _session_view(row)


async def current_conversation(session_id: int, idle_minutes: int) -> dict:
    """
    返回买家当前会话；第一次来或隔了 idle_minutes 以上再来时开新会话。
    人工接待未结束时不开新会话，买家的消息要继续进坐席队列。
    """
    async with database.SessionLocal() as session, session.begin():
        row = await session.scalar(select(ChannelSession).where(ChannelSession.id == session_id).with_for_update())
        now = _now()
        fresh = row.conversation_id is None
        if not fresh and row.last_inbound_at is not None and now - row.last_inbound_at > timedelta(minutes=idle_minutes):
            open_handoff = await session.scalar(select(Handoff.id).where(
                Handoff.conversation_id == row.conversation_id, Handoff.status.in_(OPEN_HANDOFF)))
            fresh = open_handoff is None
        if fresh:
            conversation = Conversation(user_id=row.user_id)
            session.add(conversation)
            await session.flush()
            row.conversation_id = conversation.id
        row.last_inbound_at = now
        return {**_session_view(row), "new": fresh}


async def session_for_conversation(conversation_id: int) -> dict | None:
    async with database.SessionLocal() as session:
        row = await session.scalar(select(ChannelSession).where(ChannelSession.conversation_id == conversation_id))
        return _session_view(row) if row else None


# ==================== 收发记录 ====================

async def record_inbound(channel: str, session_id: int, external_id: str, kind: str, content: str) -> int | None:
    """登记入站消息；同一平台消息 ID 已登记过（平台重试）返回 None。"""
    async with database.SessionLocal() as session:
        row = ChannelMessage(channel=channel, session_id=session_id, direction="in", external_id=external_id,
                             kind=kind, content=content, status="pending", created_at=_now(), updated_at=_now())
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        return row.id


async def finish_inbound(ids: list[int], status: str, conversation_id: int | None = None,
                         error: str | None = None) -> None:
    if not ids:
        return
    async with database.SessionLocal() as session, session.begin():
        await session.execute(update(ChannelMessage).where(ChannelMessage.id.in_(ids)).values(
            status=status, conversation_id=conversation_id, error=(error or None) and error[:255],
            updated_at=_now()))


async def pending_inbound(channel: str, since_minutes: int) -> list[dict]:
    """进程重启前没处理完的入站消息（只补处理最近的，太久的买家早已离开）。"""
    since = _now() - timedelta(minutes=since_minutes)
    async with database.SessionLocal() as session:
        rows = await session.scalars(select(ChannelMessage).where(
            ChannelMessage.channel == channel, ChannelMessage.direction == "in",
            ChannelMessage.status == "pending", ChannelMessage.created_at >= since,
        ).order_by(ChannelMessage.id))
        return [{"id": row.id, "session_id": row.session_id, "kind": row.kind, "content": row.content}
                for row in rows]


async def expire_pending(channel: str, before_minutes: int) -> int:
    before = _now() - timedelta(minutes=before_minutes)
    async with database.SessionLocal() as session, session.begin():
        result = await session.execute(update(ChannelMessage).where(
            ChannelMessage.channel == channel, ChannelMessage.direction == "in",
            ChannelMessage.status == "pending", ChannelMessage.created_at < before,
        ).values(status="expired", updated_at=_now()))
        return int(result.rowcount or 0)


async def get_session(session_id: int) -> dict | None:
    async with database.SessionLocal() as session:
        row = await session.get(ChannelSession, session_id)
        return _session_view(row) if row else None


async def record_outbound(channel: str, session_id: int, kind: str, content: str, status: str, *,
                          attempts: int = 0, error: str | None = None, conversation_id: int | None = None) -> None:
    async with database.SessionLocal() as session, session.begin():
        session.add(ChannelMessage(channel=channel, session_id=session_id, direction="out", kind=kind,
                                   content=content, status=status, attempts=attempts,
                                   error=(error or None) and error[:255], conversation_id=conversation_id,
                                   created_at=_now(), updated_at=_now()))


async def stats(channel: str, hours: int = 24) -> dict:
    since = _now() - timedelta(hours=hours)
    async with database.SessionLocal() as session:
        rows = (await session.execute(
            select(ChannelMessage.direction, ChannelMessage.status, func.count())
            .where(ChannelMessage.channel == channel, ChannelMessage.created_at >= since)
            .group_by(ChannelMessage.direction, ChannelMessage.status))).all()
        buyers = await session.scalar(select(func.count()).select_from(ChannelSession).where(
            ChannelSession.channel == channel, ChannelSession.last_inbound_at >= since))
        failures = await session.scalars(select(ChannelMessage).where(
            ChannelMessage.channel == channel, ChannelMessage.status == "failed",
        ).order_by(ChannelMessage.id.desc()).limit(10))
        recent_failures = [{"id": row.id, "direction": row.direction, "kind": row.kind, "error": row.error,
                            "conversation_id": row.conversation_id,
                            "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None}
                           for row in failures]
    counts = {"in": {}, "out": {}}
    for direction, status, count in rows:
        counts.setdefault(direction, {})[status] = int(count)
    return {"hours": hours, "buyers": int(buyers or 0), "inbound": counts["in"], "outbound": counts["out"],
            "recent_failures": recent_failures}


# ==================== 订单归属 ====================

async def attest_order(channel: str, order_id: str, user_id: str, goods_name: str | None = None) -> bool:
    """登记买家发来的订单卡片。订单已登记在别的买家名下时不改（返回 False）。"""
    async with database.SessionLocal() as session:
        row = await session.scalar(select(ChannelOrder).where(ChannelOrder.channel == channel,
                                                              ChannelOrder.order_id == order_id))
        if row is not None:
            if row.user_id != user_id:
                logger.warning("订单已登记在其他买家名下 channel=%s", channel)
                return False
            if goods_name and not row.goods_name:
                row.goods_name = goods_name[:255]
                await session.commit()
            return True
        session.add(ChannelOrder(channel=channel, order_id=order_id, user_id=user_id,
                                 goods_name=(goods_name or None) and goods_name[:255]))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
        return True


async def order_owner(channel: str, order_id: str) -> dict | None:
    async with database.SessionLocal() as session:
        row = await session.scalar(select(ChannelOrder).where(ChannelOrder.channel == channel,
                                                              ChannelOrder.order_id == order_id))
        return {"user_id": row.user_id, "goods_name": row.goods_name} if row else None


async def orders_for_user(channel: str, user_id: str, limit: int = 5) -> list[dict]:
    async with database.SessionLocal() as session:
        rows = await session.scalars(select(ChannelOrder).where(
            ChannelOrder.channel == channel, ChannelOrder.user_id == user_id,
        ).order_by(ChannelOrder.id.desc()).limit(limit))
        return [{"order_id": row.order_id, "goods_name": row.goods_name} for row in rows]
