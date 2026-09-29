# 模块：数据库仓储层
# 提供所有数据库操作的统一接口，封装会话、消息、工单、知识库、审核等业务实体的CRUD
# 使用SQLAlchemy异步ORM，确保并发安全和事务一致性
# 核心职责：隔离业务逻辑与数据库实现，提供类型安全的数据访问接口

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
    """
    创建会话并返回数据库ID

    参数:
        user_id: 用户ID

    返回:
        会话ID
    """
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
    """
    只读取属于当前用户的会话

    参数:
        conversation_id: 会话ID
        user_id: 用户ID

    返回:
        会话对象，不存在或不属于该用户时返回None

    设计说明:
        权限校验：确保用户只能访问自己的会话
    """
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
    """
    向会话追加一条消息

    参数:
        conversation_id: 会话ID
        role: 角色（user/assistant/tool）
        content: 消息内容
        tool_calls: 工具调用列表
        tool_call_id: 工具调用ID（tool消息）

    返回:
        消息ID
    """
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
    """
    按写入顺序读取会话消息

    参数:
        conversation_id: 会话ID

    返回:
        消息列表，按ID升序
    """
    async with SessionLocal() as session:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id)
        )
        result = await session.scalars(statement)
        return list(result)

async def list_conversations(user_id: str) -> list[Conversation]:
    """
    读取当前用户的会话列表

    参数:
        user_id: 用户ID

    返回:
        会话列表，按ID降序（最新的在前）
    """
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
    """
    只返回前端需要显示的用户和最终模型消息

    参数:
        conversation_id: 会话ID

    返回:
        过滤后的消息列表

    过滤规则:
        - 保留所有user消息
        - 只保留有内容且无tool_calls的assistant消息
        - 过滤tool消息和中间assistant消息

    设计说明:
        前端对话气泡只展示用户问题和最终答案
        工具调用过程对用户透明
    """
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
    """
    插入知识块到数据库

    参数:
        category: 知识分类
        questions: 问题文本（换行分隔多个问题）
        answer: 答案文本
        section_path: 章节路径（可选）
        content_type: 内容类型（可选）
        is_key_clause: 是否关键条款（0或1）

    返回:
        知识块ID

    设计说明:
        初始状态为pending，等待向量化流程处理
    """
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
    """
    列出所有待向量化的知识块

    返回:
        待处理的知识块列表，按ID升序

    设计说明:
        向量化任务调度器的数据源
    """
    async with SessionLocal() as session:
        statement = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.vectorize_status == "pending")
            .order_by(KnowledgeChunk.id)
        )
        result = await session.scalars(statement)
        return list(result)


async def mark_chunk_vectorized(chunk_id: int, vector_id: str) -> None:
    """
    标记知识块已完成向量化

    参数:
        chunk_id: 知识块ID
        vector_id: 向量数据库中的ID

    设计说明:
        原子更新状态和向量ID，确保不会重复向量化
    """
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
    """
    设置知识块的前后邻居关系

    参数:
        chunk_id: 当前知识块ID
        prev_id: 前一个知识块ID
        next_id: 后一个知识块ID

    设计说明:
        用于维护文档内知识块的顺序关系
        支持上下文连贯性检索
    """
    async with SessionLocal() as session:
        chunk = await session.get(KnowledgeChunk, chunk_id)
        if chunk is None:
            return
        chunk.prev_chunk_id = prev_id
        chunk.next_chunk_id = next_id
        await session.commit()


async def count_chunks_by_content_types(content_types: set[str]) -> int:
    """
    统计指定内容类型的知识块总数

    参数:
        content_types: 内容类型集合

    返回:
        匹配的知识块数量
    """
    async with SessionLocal() as session:
        statement = select(KnowledgeChunk).where(
            KnowledgeChunk.content_type.in_(content_types)
        )
        result = await session.scalars(statement)
        return len(list(result))


async def ensure_knowledge_chunks(chunks: list) -> list[int]:
    """
    单进程建库：复用完全相同的原文，补齐缺块和邻接关系

    参数:
        chunks: 知识块列表

    返回:
        知识块ID列表

    设计说明:
        - 一份材料在一个事务中完成
        - 旧版逐条提交留下的部分数据也能复用
        - 这是固定材料的重跑入口，不负责删除或替换已修改的旧版材料
        - 通过五元组（category, questions, answer, section_path, content_type）去重
        - 自动维护prev/next链接关系
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
    records = await list_messages(conversation_id)
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
        - 会话级锁防止并发决策
        - 幂等性：重复确认返回首次结果，避免重复建单
        - 事务一致性：决策和消息记录原子提交
        - 冲突检测：不允许同一调用作出不同决定
    """
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


def _turn_message_id(message, role: str, conversation_id: int) -> str | None:
    """
    提取LangGraph消息的turn标识

    参数:
        message: 消息对象
        role: 消息角色
        conversation_id: 会话ID

    返回:
        turn消息ID（格式：msg_{conversation_id}_{turn}），不符合格式返回None

    设计说明:
        仅处理assistant消息且ID符合特定前缀的消息
        用于增量同步时识别turn边界
    """
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
    """
    全量图历史按游标增量保存；消息和游标同事务提交，可在失败后重试

    参数:
        conversation_id: 会话ID
        user_id: 用户ID
        messages: LangGraph消息列表

    设计说明:
        - graph_sync/ticket_decision为内部记录，前端展示和模型历史恢复会忽略它们
        - 游标机制：基于last_turn_message_id判断已同步位置
        - 增量追加：只写入游标之后的新消息
        - 首次同步时尝试匹配已有消息，避免重复
        - 事务原子性：消息写入和游标更新要么都成功要么都失败
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
    """
    插入工具审计日志

    参数:
        record: 工具审计记录

    设计说明:
        - 基于audit_key幂等：重复插入相同key的记录不报错
        - 记录工具调用的性能、状态、重试次数等
        - 用于工具使用分析和故障诊断
    """
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



        async with SessionLocal() as session:
            existing_id = await session.scalar(
                select(ToolAuditLog.id).where(
                    ToolAuditLog.audit_key == record.audit_key,
                )
            )
        if existing_id is None:
            raise


async def insert_trace_span(payload: dict) -> None:
    """
    插入追踪span记录

    参数:
        payload: span数据字典

    设计说明:
        - 基于span_id幂等：重复插入相同span_id不报错
        - 记录trace的层级结构、性能、token使用量
        - 验证相同span_id的数据一致性
        - 用于可观测性分析和成本统计
    """
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
    """
    列出trace的所有span记录

    参数:
        trace_id: 追踪ID

    返回:
        span字典列表，按创建时间和span_id排序

    设计说明:
        用于trace详情查看和调试
    """
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
    """
    保存回答快照。快照不可变，重复调用必须完全相同

    参数:
        owner: 用户ID
        conversation: 会话ID（字符串形式）
        message_id: 消息ID（assistant回答的稳定标识）
        turn_id: 轮次ID
        question: 原始问题
        snapshot: 检索快照列表，None表示快照丢失，[]表示检索零命中

    设计说明:
        - 快照不可变：相同message_id的重复保存必须数据完全一致
        - 用于低置信度问题的回溯分析
        - 记录检索结果以便后续改进
    """
    snapshot_json = json.dumps(snapshot, ensure_ascii=False) if snapshot is not None else None

    async with SessionLocal() as session:

        statement = select(Turn).where(
            Turn.owner == owner,
            Turn.conversation == conversation,
            Turn.message_id == message_id,
        )
        existing = await session.scalar(statement)

        if existing is not None:

            if (existing.turn_id != turn_id or
                    existing.question != question or
                    existing.snapshot != snapshot_json):
                raise ValueError("immutable turn snapshot conflict")
            return


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
    """
    将回答落入问题池。必须先调用save_turn保存快照

    参数:
        owner: 用户ID
        conversation: 会话ID
        message_id: 消息ID
        source: 来源（retrieval_low_conf/self_check/user_feedback）
        reason: 原因描述

    返回:
        问题池记录ID

    异常:
        ValueError: source不合法
        PermissionError: 找不到对应的快照（可能是越权访问）

    设计说明:
        - 必须先调用save_turn保存快照
        - 幂等性：相同owner+conversation+message_id+source的重复调用返回首次创建的ID
        - 用于收集需要改进的问题
    """
    valid_sources = {"retrieval_low_conf", "self_check", "user_feedback"}
    if source not in valid_sources:
        raise ValueError(f"invalid source: {source}")

    async with SessionLocal() as session:

        statement = select(Turn).where(
            Turn.owner == owner,
            Turn.conversation == conversation,
            Turn.message_id == message_id,
        )
        turn = await session.scalar(statement)

        if turn is None:
            raise PermissionError("answer not found for this owner/conversation")


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
    """
    提交用户反馈。只有down会落池，up不处理

    参数:
        owner: 用户ID
        conversation: 会话ID
        message_id: 消息ID
        rating: 评分（up/down）

    返回:
        问题池记录ID，如果是up则返回None

    异常:
        ValueError: rating不合法
        PermissionError: 找不到对应的快照（可能是越权访问）

    设计说明:
        - up反馈不做处理，仅记录验证权限
        - down反馈自动调用capture_low_confidence落入问题池
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


    return await capture_low_confidence(
        owner=owner,
        conversation=conversation,
        message_id=message_id,
        source="user_feedback",
        reason="user_reports_unresolved",
    )


async def list_unmatched_questions(limit: int = 100) -> list[dict]:
    """
    查询未匹配的问题池记录

    参数:
        limit: 返回数量上限

    返回:
        未匹配的问题列表，每项包含id, question, snapshot等字段

    设计说明:
        用于问题池处理流程，筛选尚未关联到审核项的问题
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
    """
    查询所有待审核项作为匹配候选

    参数:
        limit: 返回数量上限

    返回:
        候选列表，每项包含id, question, status

    设计说明:
        用于问题归并时提供匹配目标
        按ID降序返回最新的审核项
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
    """
    原子归并：创建/加频次 + 回填游标

    参数:
        pool_id: 问题池记录ID
        question: 标准化后的问题
        suggestion: 建议回答
        matched_id: 匹配到的review_id，None表示新建
        offered_ids: 候选集合，防止幻觉ID

    返回:
        (review_id, action)
        action: "created" | "merged" | "already"

    异常:
        ValueError: 参数验证失败、幻觉ID、匹配消失等

    设计说明:
        - 事务保证：review创建/更新与问题池回填同时成功或失败
        - 幂等性：已归并的问题重复调用返回"already"
        - 防护：matched_id必须在offered_ids中，防止模型幻觉ID
        - 频次累加：相同问题归并到同一review时增加occurrences
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty string")

    if not isinstance(suggestion, str):
        raise ValueError("suggestion must be string")


    if matched_id is not None and (
        type(matched_id) is not int or matched_id not in offered_ids
    ):
        raise ValueError("hallucinated match")

    async with SessionLocal() as session:
        async with session.begin():

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


            if matched_id is None:

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


            pool_row.review_id = review_id

        return review_id, action


def _review_data(row: Review) -> dict:
    """
    将Review对象转换为字典

    参数:
        row: Review对象

    返回:
        审核项字典

    设计说明:
        统一的序列化方法，确保API返回格式一致
    """
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
    """
    列出审核队列

    参数:
        status: 状态过滤（pending/publishing/approved/rejected），None表示全部
        limit: 返回数量上限（1-100）

    返回:
        审核项列表，按ID降序

    异常:
        ValueError: 参数验证失败

    设计说明:
        用于审核管理面板的列表视图
    """
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
    """
    获取审核项详情

    参数:
        review_id: 审核项ID

    返回:
        审核项详细信息，不存在时返回None

    设计说明:
        包含关联的问题池记录，用于审核决策
    """
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
    """
    驳回审核项

    参数:
        review_id: 审核项ID
        reviewer: 审核人

    返回:
        更新后的审核项

    异常:
        ValueError: 参数验证失败或状态不符
        LookupError: 审核项不存在

    设计说明:
        - 只能驳回pending状态的审核项
        - 已驳回的重复调用幂等返回
        - 记录审核人和审核时间
    """
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
    """
    核准审核项

    参数:
        review_id: 审核项ID
        reviewer: 审核人
        answer: 核准的答案
        source_ref: 来源引用
        source_digest: 材料版本SHA256

    返回:
        更新后的审核项

    异常:
        ValueError: 参数验证失败或状态不符
        LookupError: 审核项不存在

    设计说明:
        - 只能核准pending状态的审核项
        - 核准后状态变为publishing，等待发布
        - 已publishing/approved的重复调用需参数完全一致才幂等
        - 已冻结的审核项不能修改，需新建修订
        - source_digest用于版本控制，防止基于过期材料审核
    """
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
    """
    将知识块对象转换为发布数据字典

    参数:
        row: KnowledgeChunk对象

    返回:
        发布数据字典

    设计说明:
        用于审核发布流程的数据传递
    """
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
    """
    SQL事务里复用或创建一个冻结审核项对应的知识块

    参数:
        review_id: 审核项ID
        content_type: 内容类型

    返回:
        知识块数据字典

    异常:
        LookupError: 审核项不存在
        ValueError: 状态不符或数据不一致

    设计说明:
        - 事务保证：审核项和知识块状态一致
        - 幂等性：已存在的知识块会被复用
        - 一致性校验：复用时验证问答内容是否与审核项一致
        - 知识块初始状态为pending，等待向量化
    """
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
    """
    只在目标向量可见后调用；审核状态和SQL向量状态一起提交

    参数:
        review_id: 审核项ID
        chunk_id: 知识块ID

    返回:
        更新后的审核项

    异常:
        LookupError: 审核项不存在
        ValueError: 状态不符或关联无效

    设计说明:
        - 事务保证：审核状态和知识块向量化状态原子更新
        - 调用时机：向量已写入Milvus且可检索后
        - 清除错误标记：发布成功后清空publish_error
    """
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
    """
    记录审核发布错误

    参数:
        review_id: 审核项ID
        code: 错误代码

    设计说明:
        - 只记录publishing状态的审核项错误
        - 错误代码截断到255字符
        - 用于故障诊断和重试逻辑
    """
    async with SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is not None and review.status == "publishing":
                review.publish_error = code[:255]


async def save_eval_run(report: dict) -> int:
    """
    保存评估运行报告

    参数:
        report: 评估报告字典

    返回:
        评估运行ID

    设计说明:
        记录评估指标用于持续改进
    """
    async with SessionLocal() as session:
        row = EvalRun(**report)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def list_eval_runs(limit: int = 10) -> list[dict]:
    """
    列出评估运行记录

    参数:
        limit: 返回数量上限

    返回:
        评估运行列表，按ID降序

    设计说明:
        用于评估历史查看和指标对比
    """
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
    """
    获取知识库统计信息

    返回:
        统计数据字典，包含总数、状态分布、类型分布、关键条款数

    设计说明:
        用于知识库管理面板的概览视图
    """
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
    """
    列出最近的知识块

    参数:
        limit: 返回数量上限

    返回:
        知识块列表，按ID降序

    设计说明:
        用于知识库管理的最近更新视图
    """
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(KnowledgeChunk).order_by(KnowledgeChunk.id.desc()).limit(limit)
        )
        return list(rows)


async def list_chunk_pairs() -> list[tuple[str, str]]:
    """
    列出所有知识块的问答对

    返回:
        (questions, answer)元组列表

    设计说明:
        去重键包含问题和答案
        用于去重检查和数据导出
    """
    async with SessionLocal() as session:
        rows = await session.execute(
            select(KnowledgeChunk.questions, KnowledgeChunk.answer)
        )
        return [(question, answer) for question, answer in rows.all()]


async def staging_stats() -> dict:
    """
    获取QA提取暂存区统计信息

    返回:
        统计数据字典，包含各状态计数、总数、批次数、最新批次号

    设计说明:
        用于QA提取管理面板的概览视图
    """
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
    """
    按状态列出暂存区记录

    参数:
        status: 状态（extracted/kept/discarded）

    返回:
        暂存区记录列表，按ID升序

    设计说明:
        用于QA提取的人工审核流程
    """
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
    """
    按ID列表查询暂存区记录

    参数:
        ids: ID列表
        status: 可选状态过滤

    返回:
        暂存区记录列表，按ID升序

    设计说明:
        用于批量操作时的数据获取
    """
    if not ids:
        return []
    async with SessionLocal() as session:
        query = select(QaExtractionStaging).where(QaExtractionStaging.id.in_(ids))
        if status is not None:
            query = query.where(QaExtractionStaging.status == status)
        rows = await session.scalars(query.order_by(QaExtractionStaging.id))
        return list(rows)


async def set_staging_status(ids: list[int], status: str) -> None:
    """
    批量设置暂存区记录状态

    参数:
        ids: ID列表
        status: 目标状态

    设计说明:
        - 事务保证：全部更新或全部失败
        - 行级锁：防止并发冲突
        - 用于批量保留/丢弃操作
    """
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




def _pool_text_stmt():
    """
    构建问题池文本查询语句

    返回:
        SQLAlchemy查询语句

    设计说明:
        标准化问法对应Review.question
        关联LowConfidenceQuestion和Review表
        返回question_id, 原始问题, 标准化问题
    """
    return (
        select(LowConfidenceQuestion.id, LowConfidenceQuestion.question, Review.question)
        .outerjoin(Review, LowConfidenceQuestion.review_id == Review.id)
        .order_by(LowConfidenceQuestion.id)
    )


async def list_pool_texts() -> list[dict]:
    """
    列出问题池的所有文本

    返回:
        问题文本列表，包含question_id和text

    设计说明:
        用于主题分类和文本分析
        优先使用标准化问题（normalized），不存在时使用原始问题（raw）
    """
    async with SessionLocal() as session:
        rows = (await session.execute(_pool_text_stmt())).all()
    return [{"question_id": qid, "text": normalized or raw}
            for qid, raw, normalized in rows]


async def list_history_user_texts() -> list[dict]:
    """
    只读历史用户提问；供问题池尚为空时构建有来源标记的语料

    返回:
        用户消息列表，包含message_id, text, asked_at

    设计说明:
        用于冷启动场景，从历史对话构建训练语料
        过滤空消息和纯空白消息
    """
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
    """
    只把已归并、尚未归类的问题送入旁路分类器

    参数:
        limit: 返回数量上限

    返回:
        未分类问题列表，包含question_id, text

    异常:
        ValueError: limit非正数

    设计说明:
        只处理已关联review_id的问题（已归并）
        排除已有分类结果的问题
        用于主题分类的增量处理
    """
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
    """
    批量插入主题分类结果

    参数:
        rows: 分类结果列表，每项包含question_id和labels

    返回:
        插入的记录数

    异常:
        ValueError: question_id重复或labels无效

    设计说明:
        - 验证question_id唯一性
        - 验证labels格式：非空列表、元素为有效topic、无重复
        - 使用17类分类体系（TOPIC_NAMES）
    """
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
    """
    获取17类主题分布统计

    参数:
        samples_per_class: 每类返回的样例数

    返回:
        分布统计字典，包含总数、最新分类时间、各类别计数和样例

    设计说明:
        直接读取本项目归类结果
        多标签问题在每个类别中都计数
        优先使用标准化问题文本
    """
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
    """
    按类目分页查询问题

    参数:
        label: 主题标签
        page: 页码（从1开始）
        size: 每页大小

    返回:
        分页结果字典，包含items, page, size, total, pages

    设计说明:
        多标签问题在每个命中类目中都可见
        返回问题详情包括分类信息、来源、归并状态等
    """
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
