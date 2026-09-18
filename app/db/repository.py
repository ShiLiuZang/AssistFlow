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
        for tool_call in reversed(record.tool_calls or []):
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
