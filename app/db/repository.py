import json
from uuid import uuid4
from app.core.conversation_lock import conversation_lock
from sqlalchemy import select
from datetime import datetime
from app.db.database import SessionLocal
from app.db.models import Conversation, KnowledgeChunk, Message, Ticket

async def create_conversation(user_id: str) -> int:
    """创建会话并返回数据库 ID。"""
    async with SessionLocal() as session:
        conversation = Conversation(user_id=user_id)
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        return conversation.id


async def get_conversation(
    conversation_id: int,
    user_id: str,
) -> Conversation | None:
    """只读取属于当前用户的会话。"""
    async with SessionLocal() as session:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        return await session.scalar(statement)
async def append_message(
    conversation_id: int,
    role: str,
    content: str | None = None,
    *,
    tool_calls: list | None = None,
    tool_call_id: str | None = None,
) -> int:
    """向会话追加一条消息。"""
    async with SessionLocal() as session:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,

        )
        session.add(message)
        await session.commit()
        await session.refresh(message)

        return message.id
async def list_messages(conversation_id: int) -> list[Message]:
    """按写入顺序读取会话消息。"""
    async with SessionLocal() as session:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id)
        )
        result = await session.scalars(statement)
        return list(result)

async def list_conversations(user_id: str) -> list[Conversation]:
    """读取当前用户的会话列表。"""
    async with SessionLocal() as session:
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.id.desc())
        )
        result = await session.scalars(statement)
        return list(result)


async def list_dialog_messages(
    conversation_id: int,
) -> list[Message]:
    """只返回前端需要显示的用户和最终模型消息。"""
    records = await list_messages(conversation_id)

    return [
        record
        for record in records
        if record.role == "user"
        or (
            record.role == "assistant"
            and not record.tool_calls
            and record.content
        )
    ]
async def create_ticket(
    conversation_id: int,
    ticket_type: str,
    description: str,
) -> str:
    """创建工单并返回用户可见的工单号。"""
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
    """读取会话中最近一条尚未产生 ToolMessage 的建单请求。"""
    records = await list_messages(conversation_id)
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


async def insert_knowledge_chunk(
    category: str,
    questions: str,
    answer: str,
    section_path: str | None = None,
    content_type: str | None = None,
    is_key_clause: int = 0,
) -> int:
    async with SessionLocal() as session:
        chunk = KnowledgeChunk(
            category=category,
            questions=questions,
            answer=answer,
            section_path=section_path,
            content_type=content_type,
            is_key_clause=is_key_clause,
        )
        session.add(chunk)
        await session.commit()
        await session.refresh(chunk)
        return chunk.id


async def list_pending_chunks() -> list[KnowledgeChunk]:
    async with SessionLocal() as session:
        statement = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.vectorize_status == "pending")
            .order_by(KnowledgeChunk.id)
        )
        result = await session.scalars(statement)
        return list(result)


async def mark_chunk_vectorized(chunk_id: int, vector_id: str) -> None:
    async with SessionLocal() as session:
        chunk = await session.get(KnowledgeChunk, chunk_id)
        if chunk is None:
            return
        chunk.vector_id = vector_id
        chunk.vectorize_status = "done"
        await session.commit()


async def set_chunk_neighbors(
    chunk_id: int,
    prev_id: int | None,
    next_id: int | None,
) -> None:
    async with SessionLocal() as session:
        chunk = await session.get(KnowledgeChunk, chunk_id)
        if chunk is None:
            return
        chunk.prev_chunk_id = prev_id
        chunk.next_chunk_id = next_id
        await session.commit()


async def count_chunks_by_content_types(content_types: set[str]) -> int:
    async with SessionLocal() as session:
        statement = select(KnowledgeChunk).where(
            KnowledgeChunk.content_type.in_(content_types)
        )
        result = await session.scalars(statement)
        return len(list(result))


async def ensure_knowledge_chunks(chunks: list) -> list[int]:
    """单进程建库：复用完全相同的原文，补齐缺块和邻接关系。

    一份材料在一个事务中完成；旧版逐条提交留下的部分数据也能复用。
    这是固定材料的重跑入口，不负责删除或替换已修改的旧版材料。
    """
    async with SessionLocal() as session:
        rows = []
        used = set()
        for chunk in chunks:
            statement = select(KnowledgeChunk).where(
                KnowledgeChunk.category == chunk.category,
                KnowledgeChunk.questions == chunk.questions,
                KnowledgeChunk.answer == chunk.answer,
                KnowledgeChunk.section_path == chunk.section_path,
                KnowledgeChunk.content_type == chunk.content_type,
            ).order_by(KnowledgeChunk.id)
            matches = list(await session.scalars(statement))
            row = next((item for item in matches if item.id not in used), None)
            if row is None:
                row = KnowledgeChunk(
                    category=chunk.category, questions=chunk.questions,
                    answer=chunk.answer, section_path=chunk.section_path,
                    content_type=chunk.content_type, is_key_clause=chunk.is_key_clause,
                )
                session.add(row)
                await session.flush()
            used.add(row.id)
            rows.append(row)
        for index, row in enumerate(rows):
            row.prev_chunk_id = rows[index - 1].id if index else None
            row.next_chunk_id = rows[index + 1].id if index + 1 < len(rows) else None
        await session.commit()
        return [row.id for row in rows]


async def get_ticket_decision(conversation_id: int, call_id: str) -> dict | None:
    records = await list_messages(conversation_id)
    for record in reversed(records):
        if record.role in {"ticket_decision", "tool"} and record.tool_call_id == call_id:
            result = json.loads(record.content or "{}")
            if "confirmed" in result:
                return result
    return None


async def decide_ticket(conversation_id: int, user_id: str, call_id: str,
                        confirmed: bool, *, graph: bool = False) -> dict:
    """建单与决定同事务提交。相同调用的重试返回首次决定，不再次建单。"""
    async with conversation_lock(user_id, conversation_id):
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
                                description=str(args.get("description") or ""))
                session.add(ticket)
                await session.flush()
                ticket.ticket_no = f"T{datetime.now():%Y%m%d}{ticket.id:04d}"
                result = {"confirmed": True, "ticket_no": ticket.ticket_no}
            else:
                result = {"confirmed": False, "message": "用户取消建单"}
            # 图的决定单独记录；ToolMessage 随图历史按顺序同步，避免多调用协议被打断。
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
    return (f"工单已创建，工单号：{result['ticket_no']}" if result["confirmed"]
            else "已取消，本次没有创建工单。")


async def persist_graph_messages(conversation_id: int, user_id: str, messages: list) -> None:
    """全量图历史按游标增量保存；消息和游标同事务提交，可在失败后重试。

    graph_sync/ticket_decision 为内部记录，既有展示和模型历史恢复会忽略它们。
    """
    async with conversation_lock(user_id, conversation_id):
        async with SessionLocal() as session, session.begin():
            owner = await session.scalar(select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id,
            ).with_for_update())
            if owner is None:
                raise ValueError("会话不存在")
            marker = await session.scalar(select(Message).where(
                Message.conversation_id == conversation_id, Message.role == "graph_sync",
            ).order_by(Message.id.desc()))
            start = int(marker.content) if marker else 0
            if marker is None:
                # 兼容此前已经落库、但尚未记录同步游标的图历史。
                existing = list(await session.scalars(select(Message).where(
                    Message.conversation_id == conversation_id,
                ).order_by(Message.id)))
                position = 0
                for message in messages:
                    role = {"human": "user", "ai": "assistant", "tool": "tool"}.get(message.type)
                    found = next((i for i in range(position, len(existing))
                                  if existing[i].role == role
                                  and existing[i].content == str(message.content)
                                  and (existing[i].tool_calls or []) == (getattr(message, "tool_calls", []) or [])
                                  and existing[i].tool_call_id == getattr(message, "tool_call_id", None)), None)
                    if found is None:
                        break
                    position = found + 1
                    start += 1
            if start > len(messages):
                raise ValueError("图历史与已保存游标不一致")
            for message in messages[start:]:
                role = {"human": "user", "ai": "assistant", "tool": "tool"}.get(message.type)
                if role is None:
                    raise ValueError("不支持的图消息类型")
                session.add(Message(
                    conversation_id=conversation_id, role=role, content=str(message.content),
                    tool_calls=getattr(message, "tool_calls", None) or None,
                    tool_call_id=getattr(message, "tool_call_id", None),
                ))
            if marker:
                marker.content = str(len(messages))
            else:
                session.add(Message(conversation_id=conversation_id, role="graph_sync",
                                    content=str(len(messages))))
