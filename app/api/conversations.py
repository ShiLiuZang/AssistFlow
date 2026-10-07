"""
会话管理API路由模块

本模块提供会话列表和消息历史的查询接口。
核心功能包括：查询用户的所有会话、查询指定会话的消息历史。
在系统中充当会话数据的只读访问层，供前端展示历史对话使用。
"""

from fastapi import APIRouter, HTTPException

from app.db import conversation_repo


router = APIRouter(tags=["conversations"])


@router.get("/api/conversations")
async def list_conversations(user_id: str) -> list[dict]:
    """
    获取指定用户的所有会话列表

    参数:
        user_id: 用户标识

    返回:
        会话列表，每个会话包含id和created_at字段

    返回格式为字典列表，便于前端展示会话卡片
    """
    conversations = await conversation_repo.list_conversations(user_id)

    return [
        {
            "id": item.id,
            "created_at": item.created_at.isoformat(),
        }
        for item in conversations
    ]


@router.get("/api/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: int,
    user_id: str,
) -> list[dict]:
    """
    获取指定会话的消息历史

    参数:
        conversation_id: 会话ID（路径参数）
        user_id: 用户标识（查询参数，用于权限校验）

    返回:
        消息列表，每条消息包含role、content、message_id字段

    核心逻辑：
    1. 先校验会话存在性和所属权
    2. 查询对话消息（过滤掉工具消息）
    3. 转换为前端需要的格式

    边界情况：
    - 会话不存在或不属于该用户时返回404
    """
    # 校验会话存在性和所属权
    conversation = await conversation_repo.get_conversation(
        conversation_id,
        user_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在",
        )

    # 查询对话消息（不包括tool角色）
    messages = await conversation_repo.list_dialog_messages(conversation_id)

    return [
        {
            "role": item.role,
            "content": item.content,
            "message_id": item.turn_message_id,
        }
        for item in messages
    ]
