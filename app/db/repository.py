import json
from uuid import uuid4
from app.core.conversation_lock import conversation_lock
from sqlalchemy import func, select
from datetime import datetime, timezone
from app.db.database import SessionLocal
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Conversation, KnowledgeChunk, Message, Ticket, ToolAuditLog,
    TraceSpan, Turn, LowConfidenceQuestion, Review, EvalRun, QaExtractionStaging,
    TopicClassification,
)
from app.tools.audit import ToolAuditRecord


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


def _turn_message_id(message, role: str, conversation_id: int) -> str | None:
    message_id = getattr(message, "id", None)
    prefix = f"msg_{conversation_id}_"
    if (
        role == "assistant"
        and isinstance(message_id, str)
        and message_id.startswith(prefix)
    ):
        return message_id
    return None


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
                    turn_message_id = _turn_message_id(
                        message,
                        role or "",
                        conversation_id,
                    )
                    found = next((i for i in range(position, len(existing))
                                  if existing[i].role == role
                                  and existing[i].content == str(message.content)
                                  and (existing[i].tool_calls or []) == (getattr(message, "tool_calls", []) or [])
                                  and existing[i].tool_call_id == getattr(message, "tool_call_id", None)
                                  and existing[i].turn_message_id == turn_message_id), None)
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
                turn_message_id = _turn_message_id(
                    message,
                    role,
                    conversation_id,
                )
                session.add(Message(
                    conversation_id=conversation_id, role=role, content=str(message.content),
                    tool_calls=getattr(message, "tool_calls", None) or None,
                    tool_call_id=getattr(message, "tool_call_id", None),
                    turn_message_id=turn_message_id,
                ))
            if marker:
                marker.content = str(len(messages))
            else:
                session.add(Message(conversation_id=conversation_id, role="graph_sync",
                                    content=str(len(messages))))


async def insert_tool_audit(record: ToolAuditRecord) -> None:
    row = ToolAuditLog(
        audit_key=record.audit_key,
        tool_call_id=record.tool_call_id,
        conversation_id=record.conversation_id,
        tool_name=record.tool_name,
        source=record.source,
        server=record.server,
        status=record.status,
        duration_ms=record.duration_ms,
        retry_count=record.retry_count,
        argument_fields=list(record.argument_fields),
        result_chars=record.result_chars,
        created_at=record.created_at,
    )

    try:
        async with SessionLocal() as session, session.begin():
            session.add(row)
    except IntegrityError:
        if record.audit_key is None:
            raise

        # 只把“相同审计键已经存在”当作幂等重放。
        # 若是其他数据库约束失败，仍交给外层审计边界记录。
        async with SessionLocal() as session:
            existing_id = await session.scalar(
                select(ToolAuditLog.id).where(
                    ToolAuditLog.audit_key == record.audit_key,
                )
            )
        if existing_id is None:
            raise


async def insert_trace_span(payload: dict) -> None:
    values = {
        "span_id": payload["span_id"],
        "trace_id": payload["trace_id"],
        "parent_id": payload.get("parent_id"),
        "name": payload["name"],
        "status": payload["status"],
        "duration_ms": payload["duration_ms"],
        "error_type": payload.get("error_type"),
        "kind": payload.get("kind", "span"),
        "intent": payload.get("intent"),
        "model": payload.get("model"),
        "input_tokens": payload.get("input_tokens"),
        "output_tokens": payload.get("output_tokens"),
        "total_tokens": payload.get("total_tokens"),
    }

    try:
        async with SessionLocal() as session, session.begin():
            session.add(TraceSpan(**values))
    except IntegrityError:
        async with SessionLocal() as session:
            existing = await session.get(
                TraceSpan,
                values["span_id"],
            )

            if existing is None:
                raise

            if any(
                getattr(existing, key) != value
                for key, value in values.items()
            ):
                raise ValueError(
                    "相同 span_id 对应不同的观测记录"
                )


async def list_trace_spans(trace_id: str) -> list[dict]:
    async with SessionLocal() as session:
        statement = (
            select(TraceSpan)
            .where(TraceSpan.trace_id == trace_id)
            .order_by(
                TraceSpan.created_at,
                TraceSpan.span_id,
            )
        )
        rows = list(await session.scalars(statement))

        return [
            {
                "trace_id": row.trace_id,
                "span_id": row.span_id,
                "parent_id": row.parent_id,
                "name": row.name,
                "status": row.status,
                "duration_ms": row.duration_ms,
                "error_type": row.error_type,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


async def save_turn(
        owner: str,
        conversation: str,
        message_id: str,
        turn_id: str,
        question: str,
        snapshot: list | None,
) -> None:
    """保存回答快照。快照不可变，重复调用必须完全相同。

    Args:
        owner: 用户ID
        conversation: 会话ID（字符串形式）
        message_id: 消息ID（assistant回答的稳定标识）
        turn_id: 轮次ID
        question: 原始问题
        snapshot: 检索快照列表，None表示快照丢失，[]表示检索零命中
    """
    snapshot_json = json.dumps(snapshot, ensure_ascii=False) if snapshot is not None else None

    async with SessionLocal() as session:
        # 检查是否已存在
        statement = select(Turn).where(
            Turn.owner == owner,
            Turn.conversation == conversation,
            Turn.message_id == message_id,
        )
        existing = await session.scalar(statement)

        if existing is not None:
            # 验证不可变性
            if (existing.turn_id != turn_id or
                    existing.question != question or
                    existing.snapshot != snapshot_json):
                raise ValueError("immutable turn snapshot conflict")
            return  # 已存在且相同，幂等返回

        # 插入新快照
        turn = Turn(
            owner=owner,
            conversation=conversation,
            message_id=message_id,
            turn_id=turn_id,
            question=question,
            snapshot=snapshot_json,
        )
        session.add(turn)
        await session.commit()


async def capture_low_confidence(
        owner: str,
        conversation: str,
        message_id: str,
        source: str,
        reason: str | None = None,
) -> int:
    """将回答落入问题池。必须先调用 save_turn 保存快照。

    Args:
        owner: 用户ID
        conversation: 会话ID
        message_id: 消息ID
        source: 来源（retrieval_low_conf/self_check/user_feedback）
        reason: 原因描述

    Returns:
        问题池记录ID

    Raises:
        ValueError: source 不合法
        PermissionError: 找不到对应的快照（可能是越权访问）
    """
    valid_sources = {"retrieval_low_conf", "self_check", "user_feedback"}
    if source not in valid_sources:
        raise ValueError(f"invalid source: {source}")

    async with SessionLocal() as session:
        # 查询快照，验证归属
        statement = select(Turn).where(
            Turn.owner == owner,
            Turn.conversation == conversation,
            Turn.message_id == message_id,
        )
        turn = await session.scalar(statement)

        if turn is None:
            raise PermissionError("answer not found for this owner/conversation")

        # 尝试插入问题池（唯一约束防重复）
        pool_record = LowConfidenceQuestion(
            owner=owner,
            conversation=conversation,
            message_id=message_id,
            question=turn.question,
            snapshot=turn.snapshot,
            source=source,
            reason=reason,
        )

        session.add(pool_record)

        try:
            await session.commit()
            await session.refresh(pool_record)
            return pool_record.id
        except IntegrityError:
            # 唯一约束冲突，说明已经落池过了
            await session.rollback()
            statement = select(LowConfidenceQuestion).where(
                LowConfidenceQuestion.owner == owner,
                LowConfidenceQuestion.conversation == conversation,
                LowConfidenceQuestion.message_id == message_id,
                LowConfidenceQuestion.source == source,
            )
            existing = await session.scalar(statement)
            return existing.id


async def submit_feedback(
        owner: str,
        conversation: str,
        message_id: str,
        rating: str,
) -> int | None:
    """提交用户反馈。只有 down 会落池，up 不处理。

    Args:
        owner: 用户ID
        conversation: 会话ID
        message_id: 消息ID
        rating: 评分（up/down）

    Returns:
        问题池记录ID，如果是 up 则返回 None

    Raises:
        ValueError: rating 不合法
        PermissionError: 找不到对应的快照（可能是越权访问）
    """
    if rating not in {"up", "down"}:
        raise ValueError(f"invalid rating: {rating}")

    if rating == "up":
        async with SessionLocal() as session:
            turn = await session.scalar(select(Turn).where(
                Turn.owner == owner,
                Turn.conversation == conversation,
                Turn.message_id == message_id,
            ))
            if turn is None:
                raise PermissionError("answer not found for this owner/conversation")
        return None

    # down 评分，落入问题池
    return await capture_low_confidence(
        owner=owner,
        conversation=conversation,
        message_id=message_id,
        source="user_feedback",
        reason="user_reports_unresolved",
    )


async def list_unmatched_questions(limit: int = 100) -> list[dict]:
    """查询未匹配的问题池记录。

    Returns:
        未匹配的问题列表，每项包含 id, question, snapshot 等字段
    """
    async with SessionLocal() as session:
        statement = select(LowConfidenceQuestion).where(
            LowConfidenceQuestion.review_id.is_(None)
        ).order_by(LowConfidenceQuestion.id).limit(limit)

        rows = await session.scalars(statement)

        return [
            {
                "id": row.id,
                "owner": row.owner,
                "conversation": row.conversation,
                "message_id": row.message_id,
                "question": row.question,
                "snapshot": row.snapshot,
                "source": row.source,
                "reason": row.reason,
            }
            for row in rows
        ]


async def list_review_candidates(limit: int = 101) -> list[dict]:
    """查询所有待审核项作为匹配候选。

    Returns:
        候选列表，每项包含 id, question, status
    """
    async with SessionLocal() as session:
        statement = select(Review).order_by(Review.id.desc()).limit(limit)
        rows = await session.scalars(statement)

        return [
            {
                "id": row.id,
                "question": row.question,
                "status": row.status,
            }
            for row in rows
        ]


async def merge_question(
    pool_id: int,
    question: str,
    suggestion: str,
    matched_id: int | None,
    offered_ids: set[int],
) -> tuple[int, str]:
    """原子归并：创建/加频次 + 回填游标。

    Args:
        pool_id: 问题池记录ID
        question: 标准化后的问题
        suggestion: 建议回答
        matched_id: 匹配到的 review_id，None 表示新建
        offered_ids: 候选集合，防止幻觉ID

    Returns:
        (review_id, action)
        action: "created" | "merged" | "already"

    Raises:
        ValueError: 参数验证失败、幻觉ID、匹配消失等
    """
    # 参数验证
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty string")

    if not isinstance(suggestion, str):
        raise ValueError("suggestion must be string")

    # 防止幻觉ID
    if matched_id is not None and (
        type(matched_id) is not int or matched_id not in offered_ids
    ):
        raise ValueError("hallucinated match")

    async with SessionLocal() as session:
        async with session.begin():
            # 检查是否已处理
            statement = (
                select(LowConfidenceQuestion)
                .where(LowConfidenceQuestion.id == pool_id)
                .with_for_update()
            )
            pool_row = await session.scalar(statement)
            if pool_row is None:
                raise ValueError("missing pool row")

            if pool_row.review_id is not None:
                return pool_row.review_id, "already"

            # 创建或归并
            if matched_id is None:
                # 创建新的待审核项
                review = Review(
                    question=question,
                    suggestion=suggestion,
                    occurrence_count=1,
                    status="pending",
                )
                session.add(review)
                await session.flush()
                review_id = review.id
                action = "created"
            else:
                # 归并到现有项
                statement = (
                    select(Review)
                    .where(Review.id == matched_id)
                    .with_for_update()
                )
                review = await session.scalar(statement)
                if review is None:
                    raise ValueError("match disappeared")

                review.occurrence_count += 1
                review_id = matched_id
                action = "merged"

            # 回填游标
            pool_row.review_id = review_id

        return review_id, action


def _review_data(row: Review) -> dict:
    return {
        "id": row.id,
        "question": row.question,
        "suggestion": row.suggestion,
        "occurrence_count": row.occurrence_count,
        "status": row.status,
        "reviewer": row.reviewer,
        "answer": row.answer,
        "source_ref": row.source_ref,
        "source_digest": row.source_digest,
        "publish_error": row.publish_error,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def list_review_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    if status not in {None, "pending", "publishing", "approved", "rejected"}:
        raise ValueError("invalid review status")
    if limit < 1 or limit > 100:
        raise ValueError("invalid review limit")
    async with SessionLocal() as session:
        statement = select(Review)
        if status is not None:
            statement = statement.where(Review.status == status)
        rows = await session.scalars(statement.order_by(Review.id.desc()).limit(limit))
        return [_review_data(row) for row in rows]


async def get_review_detail(review_id: int) -> dict | None:
    async with SessionLocal() as session:
        review = await session.get(Review, review_id)
        if review is None:
            return None
        statement = (
            select(LowConfidenceQuestion)
            .where(LowConfidenceQuestion.review_id == review_id)
            .order_by(LowConfidenceQuestion.id)
        )
        rows = await session.scalars(statement)
        return {
            **_review_data(review),
            "raws": [
                {
                    "id": row.id,
                    "raw_question": row.question,
                    "source": row.source,
                    "reason": row.reason,
                    "retrieved_chunks": json.loads(row.snapshot) if row.snapshot is not None else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ],
        }


async def reject_review(review_id: int, reviewer: str) -> dict:
    if not reviewer.strip():
        raise ValueError("审核人不能为空")
    async with SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            if review.status == "rejected":
                return _review_data(review)
            if review.status != "pending":
                raise ValueError("只有待审项可以驳回")
            review.status = "rejected"
            review.reviewer = reviewer
            review.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            return _review_data(review)


async def approve_review(
    review_id: int,
    reviewer: str,
    answer: str,
    source_ref: str,
    source_digest: str,
) -> dict:
    if not reviewer.strip() or not answer.strip() or not source_ref.strip():
        raise ValueError("审核人、核准答案和来源不能为空")
    if len(source_digest) != 64:
        raise ValueError("材料版本无效")
    async with SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            if review.status in {"publishing", "approved"}:
                if (
                    review.reviewer == reviewer
                    and review.answer == answer
                    and review.source_ref == source_ref
                    and review.source_digest == source_digest
                ):
                    return _review_data(review)
                raise ValueError("审核内容已冻结，修改答案需新建修订")
            if review.status != "pending":
                raise ValueError("已驳回项不能核准")
            review.status = "publishing"
            review.reviewer = reviewer
            review.answer = answer
            review.source_ref = source_ref
            review.source_digest = source_digest
            review.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            return _review_data(review)


def _publish_chunk_data(row: KnowledgeChunk) -> dict:
    return {
        "id": row.id,
        "review_id": row.review_id,
        "category": row.category,
        "question": row.questions,
        "answer": row.answer,
        "section_path": row.section_path,
        "content_type": row.content_type,
        "vectorize_status": row.vectorize_status,
    }


async def prepare_review_chunk(review_id: int, content_type: str) -> dict:
    """SQL 事务里复用或创建一个冻结审核项对应的知识块。"""
    async with SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            if review.status not in {"publishing", "approved"}:
                raise ValueError("审核项尚未核准")
            if not review.answer or not review.source_ref or not review.source_digest:
                raise ValueError("审核依据不完整")
            chunk = await session.scalar(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.review_id == review_id)
                .with_for_update()
            )
            if chunk is None:
                chunk = KnowledgeChunk(
                    review_id=review_id,
                    category="审核问答",
                    questions=review.question,
                    answer=review.answer,
                    section_path=f"{review.source_ref} / 审核问答",
                    content_type=content_type,
                    vectorize_status="pending",
                )
                session.add(chunk)
                await session.flush()
            elif chunk.questions != review.question or chunk.answer != review.answer:
                raise ValueError("已冻结知识块内容与审核项不一致")
            return _publish_chunk_data(chunk)


async def finish_review_publish(review_id: int, chunk_id: int) -> dict:
    """只在目标向量可见后调用；审核状态和 SQL 向量状态一起提交。"""
    async with SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            chunk = await session.scalar(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.review_id == review_id)
                .with_for_update()
            )
            if chunk is None or chunk.id != chunk_id:
                raise ValueError("审核知识块关联无效")
            if review.status not in {"publishing", "approved"}:
                raise ValueError("审核项状态不允许发布")
            chunk.vector_id = str(chunk.id)
            chunk.vectorize_status = "done"
            review.status = "approved"
            review.publish_error = None
            return _review_data(review)


async def note_review_publish_error(review_id: int, code: str) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is not None and review.status == "publishing":
                review.publish_error = code[:255]


async def save_eval_run(report: dict) -> int:
    async with SessionLocal() as session:
        row = EvalRun(**report)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def list_eval_runs(limit: int = 10) -> list[dict]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(EvalRun).order_by(EvalRun.id.desc()).limit(limit)
        )
        return [
            {
                "id": row.id,
                "dataset_version": row.dataset_version,
                "case_ids": row.case_ids,
                "config_version": row.config_version,
                "kb_revision": row.kb_revision,
                "strategy": row.strategy,
                "top_k": row.top_k,
                "triggered_by": row.triggered_by,
                "status": row.status,
                "metrics": row.metrics,
                "details": row.details,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


async def knowledge_stats() -> dict:
    """Minihelp KB page inventory from the project's existing knowledge_chunks table."""
    async with SessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(KnowledgeChunk))
        by_status = dict((await session.execute(
            select(KnowledgeChunk.vectorize_status, func.count())
            .group_by(KnowledgeChunk.vectorize_status)
        )).all())
        by_type = dict((await session.execute(
            select(KnowledgeChunk.content_type, func.count())
            .group_by(KnowledgeChunk.content_type)
        )).all())
        key_clause = await session.scalar(
            select(func.count()).select_from(KnowledgeChunk)
            .where(KnowledgeChunk.is_key_clause == 1)
        )
    return {
        "total": int(total or 0),
        "pending": int(by_status.get("pending", 0)),
        "done": int(by_status.get("done", 0)),
        "by_content_type": {(key or "未标注"): int(value)
                            for key, value in by_type.items()},
        "key_clause": int(key_clause or 0),
    }


async def list_recent_chunks(limit: int = 20) -> list[KnowledgeChunk]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(KnowledgeChunk).order_by(KnowledgeChunk.id.desc()).limit(limit)
        )
        return list(rows)


async def list_chunk_pairs() -> list[tuple[str, str]]:
    """The Minihelp dedup key includes both question and answer."""
    async with SessionLocal() as session:
        rows = await session.execute(
            select(KnowledgeChunk.questions, KnowledgeChunk.answer)
        )
        return [(question, answer) for question, answer in rows.all()]


async def staging_stats() -> dict:
    async with SessionLocal() as session:
        counts = dict((await session.execute(
            select(QaExtractionStaging.status, func.count())
            .group_by(QaExtractionStaging.status)
        )).all())
        batches = await session.scalar(
            select(func.count(func.distinct(QaExtractionStaging.batch_no)))
        )
        latest = await session.scalar(
            select(QaExtractionStaging.batch_no)
            .order_by(QaExtractionStaging.id.desc()).limit(1)
        )
    return {
        "counts": {key: int(counts.get(key, 0))
                   for key in ("extracted", "kept", "discarded")},
        "total": sum(int(value) for value in counts.values()),
        "batches": int(batches or 0),
        "latest_batch": latest,
    }


async def list_staging_by_status(status: str) -> list[QaExtractionStaging]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(QaExtractionStaging)
            .where(QaExtractionStaging.status == status)
            .order_by(QaExtractionStaging.id)
        )
        return list(rows)


async def list_staging_by_ids(
    ids: list[int], status: str | None = None,
) -> list[QaExtractionStaging]:
    if not ids:
        return []
    async with SessionLocal() as session:
        query = select(QaExtractionStaging).where(QaExtractionStaging.id.in_(ids))
        if status is not None:
            query = query.where(QaExtractionStaging.status == status)
        rows = await session.scalars(query.order_by(QaExtractionStaging.id))
        return list(rows)


async def set_staging_status(ids: list[int], status: str) -> None:
    if not ids:
        return
    async with SessionLocal() as session:
        async with session.begin():
            rows = await session.scalars(
                select(QaExtractionStaging)
                .where(QaExtractionStaging.id.in_(ids))
                .with_for_update()
            )
            for row in rows:
                row.status = status


# ---------- 微调 Minihelp topic classification adapter ----------

def _pool_text_stmt():
    """Minihelp 的标准化问法对应本项目 Review.question。"""
    return (
        select(LowConfidenceQuestion.id, LowConfidenceQuestion.question, Review.question)
        .outerjoin(Review, LowConfidenceQuestion.review_id == Review.id)
        .order_by(LowConfidenceQuestion.id)
    )


async def list_pool_texts() -> list[dict]:
    async with SessionLocal() as session:
        rows = (await session.execute(_pool_text_stmt())).all()
    return [{"question_id": qid, "text": normalized or raw}
            for qid, raw, normalized in rows]


async def list_history_user_texts() -> list[dict]:
    """只读历史用户提问；供问题池尚为空时构建有来源标记的语料。"""
    statement = (
        select(Message.id, Message.content, Message.created_at)
        .where(Message.role == "user", Message.content.is_not(None))
        .order_by(Message.id)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    return [{"message_id": message_id, "text": content.strip(),
             "asked_at": created_at.isoformat(timespec="seconds") if created_at else None}
            for message_id, content, created_at in rows if content and content.strip()]


async def list_unclassified_questions(limit: int = 500) -> list[dict]:
    """只把已归并、尚未归类的问题送入旁路分类器。"""
    if limit < 1:
        raise ValueError("limit must be positive")
    statement = (
        _pool_text_stmt()
        .outerjoin(TopicClassification,
                   TopicClassification.question_id == LowConfidenceQuestion.id)
        .where(TopicClassification.id.is_(None))
        .where(LowConfidenceQuestion.review_id.is_not(None))
        .limit(limit)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    return [{"question_id": qid, "text": normalized or raw}
            for qid, raw, normalized in rows]


async def insert_topic_classifications(rows: list[dict]) -> int:
    from app.core.taxonomy import TOPIC_NAMES

    if len({row["question_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate question id in classifier batch")
    for row in rows:
        labels = row["labels"]
        if not isinstance(labels, list) or not labels or any(
            not isinstance(label, str) or label not in TOPIC_NAMES for label in labels
        ) or len(set(labels)) != len(labels):
            raise ValueError("invalid classifier labels")
    async with SessionLocal() as session:
        session.add_all([
            TopicClassification(question_id=row["question_id"], labels=row["labels"])
            for row in rows
        ])
        await session.commit()
    return len(rows)


async def topic_distribution(samples_per_class: int = 3) -> dict:
    """Minihelp 的 17 类分布口径，直接读取本项目归类结果。"""
    from app.core.taxonomy import TOPIC_NAMES

    statement = (
        select(TopicClassification.labels, LowConfidenceQuestion.question,
               Review.question, TopicClassification.classified_at)
        .join(LowConfidenceQuestion,
              TopicClassification.question_id == LowConfidenceQuestion.id)
        .outerjoin(Review, LowConfidenceQuestion.review_id == Review.id)
        .order_by(TopicClassification.question_id)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    counts = {name: 0 for name in TOPIC_NAMES}
    samples: dict[str, list[str]] = {name: [] for name in TOPIC_NAMES}
    latest = None
    for labels, raw, normalized, stamp in rows:
        value = normalized or raw
        latest = stamp if latest is None or stamp > latest else latest
        for label in labels or []:
            if label in counts:
                counts[label] += 1
                if len(samples[label]) < samples_per_class and value not in samples[label]:
                    samples[label].append(value)
    return {
        "total": len(rows),
        "latest": latest.isoformat() if latest else None,
        "classes": [{"label": name, "count": counts[name], "samples": samples[name]}
                    for name in TOPIC_NAMES],
    }


async def topic_questions(label: str, page: int = 1, size: int = 20) -> dict:
    """按类目分页；多标签问题在每个命中类目中都可见。"""
    statement = (
        select(TopicClassification.question_id, TopicClassification.labels,
               TopicClassification.classified_at, LowConfidenceQuestion.question,
               LowConfidenceQuestion.source, LowConfidenceQuestion.created_at,
               Review.question, Review.occurrence_count, Review.status)
        .join(LowConfidenceQuestion,
              TopicClassification.question_id == LowConfidenceQuestion.id)
        .outerjoin(Review, LowConfidenceQuestion.review_id == Review.id)
        .order_by(TopicClassification.question_id.desc())
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    hits = [row for row in rows if label in (row[1] or [])]
    pages = max(1, -(-len(hits) // size))
    page = min(page, pages)
    labels = {"pending": "待审", "publishing": "发布中",
              "approved": "通过", "rejected": "驳回"}
    items = [
        {"question_id": qid, "labels": classified,
         "text": normalized or raw, "raw_question": raw,
         "normalized": normalized is not None,
         "source": source, "occurrence_count": occurrence_count,
         "review_status": labels.get(review_status),
         "asked_at": asked.isoformat() if asked else None,
         "classified_at": stamp.isoformat() if stamp else None}
        for qid, classified, stamp, raw, source, asked, normalized,
            occurrence_count, review_status in hits[(page - 1) * size: page * size]
    ]
    return {"label": label, "total": len(hits), "page": page,
            "size": size, "pages": pages, "items": items}
