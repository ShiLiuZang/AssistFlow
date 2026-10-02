from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/graph-chat 的请求体，由 FastAPI 在进入接口前自动校验。"""

    user_id: str | None = Field(
        default=None,
        description="已废弃：身份取自令牌，此字段会被忽略",
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="用户本轮发送的消息",
    )
    conversation_id: int | None = Field(
        default=None,
        description="继续已有会话时传入；第一次聊天不传",
    )
