"""会话与消息：创建与读取会话、消息历史、图消息同步"""

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Conversation, Message


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
        # 人工接待期间的顾客消息、坐席回复和接入提示；内部备注 staff_note 不给顾客看
        or record.role in {"handoff_user", "staff", "handoff_event"}
    ]


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
        - 调用方须持有会话锁（app.core.conversation_lock）
    """
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
