"""会话内工单：待确认的建单调用、顾客确认或取消（建单与决定同事务）"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.db import conversation_repo
from app.db.database import SessionLocal
from app.db.models import Conversation, Message, Ticket, TicketEvent


async def create_ticket(
    conversation_id: int,
    ticket_type: str,
    description: str,
) -> str:
    """
    创建工单并返回用户可见的工单号

    参数:
        conversation_id: 会话ID
        ticket_type: 工单类型
        description: 工单描述

    返回:
        工单号（格式：T+日期+4位序号，如T202401010001）

    设计说明:
        先插入PENDING占位符，flush后获取自增ID，再更新为格式化工单号
        保证工单号全局唯一且可读
    """
    async with SessionLocal() as session:
        ticket = Ticket(
            conversation_id=conversation_id,
            ticket_no="PENDING",
            ticket_type=ticket_type,
            description=description,
        )
        session.add(ticket)
        await session.flush()

        ticket.ticket_no = (
            f"T{datetime.now():%Y%m%d}{ticket.id:04d}"
        )

        await session.commit()
        return ticket.ticket_no


async def get_pending_ticket_call(conversation_id: int) -> dict | None:
    """
    读取会话中最近一条尚未产生ToolMessage的建单请求

    参数:
        conversation_id: 会话ID

    返回:
        待处理的tool_call字典，不存在时返回None

    设计说明:
        用于人工审核场景：模型调用create_ticket但需要人工确认
        通过比对tool_call_id判断哪些调用已响应
        倒序遍历找到最近的未决调用
    """
    records = await conversation_repo.list_messages(conversation_id)
    resolved_ids = {
        record.tool_call_id
        for record in records
        if record.role == "tool" and record.tool_call_id
    }

    for record in reversed(records):
        for tool_call in record.tool_calls or []:
            if (
                tool_call.get("name") == "create_ticket"
                and tool_call.get("id") not in resolved_ids
            ):
                return tool_call

    return None


async def get_ticket_decision(conversation_id: int, call_id: str) -> dict | None:
    """
    读取工单决策结果

    参数:
        conversation_id: 会话ID
        call_id: 工具调用ID

    返回:
        决策字典 {"confirmed": bool, ...}，不存在时返回None

    设计说明:
        倒序查找最近的决策记录
        支持graph和传统模式的决策消息
    """
    records = await conversation_repo.list_messages(conversation_id)
    for record in reversed(records):
        if record.role in {"ticket_decision", "tool"} and record.tool_call_id == call_id:
            result = json.loads(record.content or "{}")
            if "confirmed" in result:
                return result
    return None


async def decide_ticket(conversation_id: int, user_id: str, call_id: str,
                        confirmed: bool, *, graph: bool = False) -> dict:
    """
    建单与决定同事务提交，相同调用的重试返回首次决定，不再次建单

    参数:
        conversation_id: 会话ID
        user_id: 用户ID
        call_id: 工具调用ID
        confirmed: 是否确认建单
        graph: 是否为LangGraph模式

    返回:
        决策结果字典

    设计说明:
        - 调用方须持有会话锁（app.core.conversation_lock）；这里另有数据库行锁防并发
        - 幂等性：重复确认返回首次结果，避免重复建单
        - 事务一致性：决策和消息记录原子提交
        - 冲突检测：不允许同一调用作出不同决定
    """
    async with SessionLocal() as session, session.begin():
        owner = await session.scalar(select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).with_for_update())
        if owner is None:
            raise ValueError("会话不存在")
        records = list(await session.scalars(select(Message).where(
            Message.conversation_id == conversation_id,
        ).order_by(Message.id)))
        for record in reversed(records):
            if record.role in {"ticket_decision", "tool"} and record.tool_call_id == call_id:
                result = json.loads(record.content or "{}")
                if "confirmed" in result:
                    if result["confirmed"] is not confirmed:
                        raise ValueError("该调用已经作出不同决定")
                    return result
                raise ValueError("该调用已经处理，不能再次建单")
        call = next((call for record in reversed(records)
                     for call in record.tool_calls or []
                     if call.get("id") == call_id and call.get("name") == "create_ticket"), None)
        if call is None:
            raise ValueError("没有待确认的工单")
        if confirmed:
            args = call.get("args") or {}
            ticket = Ticket(conversation_id=conversation_id,
                            ticket_no="PENDING-" + uuid4().hex,
                            ticket_type=str(args.get("ticket_type") or "咨询"),
                            description=str(args.get("description") or ""),
                            user_id=user_id, source="customer", status="待处理",
                            updated_at=datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0))
            session.add(ticket)
            await session.flush()
            ticket.ticket_no = f"T{datetime.now():%Y%m%d}{ticket.id:04d}"
            session.add(TicketEvent(ticket_id=ticket.id, actor=f"customer:{user_id}", action="create",
                                    to_status="待处理", note="顾客在会话中确认创建"))
            result = {"confirmed": True, "ticket_no": ticket.ticket_no}
        else:
            result = {"confirmed": False, "message": "用户取消建单"}

        session.add(Message(conversation_id=conversation_id,
                            role="ticket_decision" if graph else "tool",
                            content=json.dumps(result, ensure_ascii=False), tool_call_id=call_id))
        if not graph:
            session.add(Message(conversation_id=conversation_id, role="user",
                                content="确认提交工单" if confirmed else "取消建单"))
            session.add(Message(conversation_id=conversation_id, role="assistant",
                                content=ticket_answer(result)))
        return result


def ticket_answer(result: dict) -> str:
    """
    生成工单创建的用户可见消息

    参数:
        result: 决策结果字典

    返回:
        用户消息文本
    """
    return (f"工单已创建，工单号：{result['ticket_no']}" if result["confirmed"]
            else "已取消，本次没有创建工单。")
