"""Database-backed adapter for the rolling summary algorithm."""
from sqlalchemy import select, update

from app.core.memory import Message as ViewMessage
from app.core.summarizer import Summary, summarize_delta
from app.db.models import Conversation, Message


class SummaryConflict(RuntimeError):
    """Another worker saved first; reload before retrying."""


class PersistentSummaryStore:
    def __init__(self, sessions=None):
        if sessions is None:
            from app.db.database import SessionLocal
            sessions = SessionLocal
        self.sessions = sessions

    async def load(self, key):
        """Read an owned conversation and its complete persisted model history."""
        user_id, conversation_id = key
        async with self.sessions() as session:
            conversation = await session.scalar(select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id,
            ))
            if conversation is None:
                raise ValueError("会话不存在")
            rows = await session.scalars(select(Message).where(
                Message.conversation_id == conversation_id,
                Message.role.in_(("user", "assistant", "tool")),
            ).order_by(Message.id))
            roles = {"user": "human", "assistant": "ai", "tool": "tool"}
            messages = [ViewMessage(
                row.id, roles[row.role], row.content or "",
                tuple(call["id"] for call in (row.tool_calls or [])), row.tool_call_id,
            ) for row in rows]
            return (Summary(conversation.summary_text or "", conversation.summary_upto),
                    conversation.summary_version, messages)

    async def update(self, key, summarize, keep=2, threshold=1):
        """Generate outside the transaction, then CAS text/cursor/version atomically."""
        if threshold < 1:
            raise ValueError("threshold must be positive")
        old, version, messages = await self.load(key)
        new = await summarize_delta(old, messages, summarize, keep=keep, threshold=threshold)
        if new == old:
            return old
        user_id, conversation_id = key
        async with self.sessions() as session, session.begin():
            result = await session.execute(update(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.summary_version == version,
                Conversation.summary_upto == old.upto,
            ).values(summary_text=new.text, summary_upto=new.upto,
                     summary_version=version + 1))
            if result.rowcount != 1:
                raise SummaryConflict("摘要版本冲突，请重新读取后重试")
        return new
