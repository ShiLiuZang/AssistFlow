from fastapi import APIRouter, HTTPException

from app.db import repository


router = APIRouter(tags=["conversations"])


@router.get("/api/conversations")
async def list_conversations(user_id: str) -> list[dict]:
    conversations = await repository.list_conversations(user_id)

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
    conversation = await repository.get_conversation(
        conversation_id,
        user_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在",
        )

    messages = await repository.list_dialog_messages(conversation_id)

    return [
        {
            "role": item.role,
            "content": item.content,
            "message_id": item.turn_message_id,
        }
        for item in messages
    ]
