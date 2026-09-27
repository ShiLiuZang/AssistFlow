from datetime import datetime
from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Integer, String, Text,
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
