from datetime import datetime
from sqlalchemy import (
    BigInteger, JSON, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_upto: Mapped[int] = mapped_column(default=0, server_default="0")
    summary_version: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    turn_message_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
    )

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"),
        index=True,
    )
    ticket_no: Mapped[str] = mapped_column(
        String(50),
        unique=True,
    )
    ticket_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20),
        default="待处理",
    )
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int | None] = mapped_column(
        ForeignKey("reviews.id"), unique=True, nullable=True,
    )
    category: Mapped[str] = mapped_column(String(255))
    questions: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    section_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_key_clause: Mapped[int] = mapped_column(default=0)
    prev_chunk_id: Mapped[int | None] = mapped_column(nullable=True)
    next_chunk_id: Mapped[int | None] = mapped_column(nullable=True)
    vector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vectorize_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class QaExtractionStaging(Base):
    """Minihelp 对话挖知识的暂存队列，人工采纳后才进入正式知识库。"""

    __tablename__ = "qa_extraction_staging"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_no: Mapped[str] = mapped_column(String(64))
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="extracted", server_default="extracted")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TopicClassification(Base):
    """微调 旁路分类结果；每条低置信度问题最多保存一次分类。"""

    __tablename__ = "topic_classifications"
    __table_args__ = (UniqueConstraint("question_id", name="uq_topic_classifications_question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("low_confidence_questions.id"), nullable=False,
    )
    labels: Mapped[list] = mapped_column(JSON, nullable=False)
    classified_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )


class ToolAuditLog(Base):
    __tablename__ = "tool_audit_logs"
    __table_args__ = (
        UniqueConstraint(
            "audit_key",
            name="uq_tool_audit_logs_audit_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    tool_call_id: Mapped[str] = mapped_column(String(100))
    conversation_id: Mapped[str] = mapped_column(
        String(64), index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16))
    server: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer)
    argument_fields: Mapped[list[str]] = mapped_column(JSON)
    result_chars: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    span_id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
    )
    trace_id: Mapped[str] = mapped_column(
        String(32),
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(
        String(16), server_default="span",
    )
    intent: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    input_tokens: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )
    output_tokens: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )
    total_tokens: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[float] = mapped_column(Float(precision=53))
    error_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )
class Turn(Base):
    """回答快照表 - 记录每次回答时的原始问题和检索结果"""
    __tablename__ = "turns"
    __table_args__ = (
        {"comment": "Conversation turn snapshots for historical reference"},
    )

    owner: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    turn_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class LowConfidenceQuestion(Base):
    """低置信度问题池 - 收集需要人工审核的问题"""
    __tablename__ = "low_confidence_questions"
    __table_args__ = (
        UniqueConstraint(
            "owner",
            "conversation",
            "message_id",
            "source",
            name="uq_pool_message_source",
        ),
        {"comment": "Low confidence questions pool for review"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    conversation: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("reviews.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )


class Review(Base):
    """待审核队列 - 标准化后的问题和归并频次"""
    __tablename__ = "reviews"
    __table_args__ = (
        {"comment": "Review queue for normalized questions"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )


class EvalRun(Base):
    """固定集的一次完整评测记录。"""
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(128))
    case_ids: Mapped[list] = mapped_column(JSON)
    config_version: Mapped[str] = mapped_column(String(128))
    kb_revision: Mapped[str] = mapped_column(String(128))
    strategy: Mapped[str] = mapped_column(String(32))
    top_k: Mapped[int] = mapped_column(Integer)
    triggered_by: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    metrics: Mapped[dict] = mapped_column(JSON)
    details: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )
