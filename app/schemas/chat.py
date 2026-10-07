from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/graph-chat 的请求体，由 FastAPI 在进入接口前自动校验。"""

    user_id: str | None = Field(
        default=None,
        min_length=1,
        description="可选兼容字段；提供时必须与访客令牌身份一致",
    )
    message: str = Field(
        min_length=1,
        description="用户本轮发送的消息",
    )
    conversation_id: int | None = Field(
        default=None,
        description="继续已有会话时传入；第一次聊天不传",
    )
