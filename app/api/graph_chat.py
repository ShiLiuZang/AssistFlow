"""
图模式聊天API路由模块

本模块实现基于LangGraph的状态图聊天接口，支持复杂的多步推理和状态管理。
核心功能包括：图状态持久化、会话历史同步、对话摘要调度、消息一致性校验。
在系统中充当高级对话管理器，适用于需要多轮规划、工具编排和上下文压缩的场景。
与chat.py的区别：使用图运行时管理状态，支持断点续传和自动摘要。
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.sse import DONE_SSE, event_to_sse, make_sse
from app.db import repository
from app.graph import turns
from app.graph.runtime import Runtime
from app.core.ratelimit import limit_customer_chat
from app.schemas.chat import ChatRequest


router = APIRouter(prefix="/api", tags=["graph-chat"])


async def stream_graph_chat(
    request: ChatRequest, conversation_id: int, runtime: Runtime,
) -> AsyncIterator[str]:
    """
    执行一轮图聊天并编码成 SSE

    先发送会话 ID，再输出 turns.chat_turn 的事件（handoff、delta、tool、citations、done、interrupt、error），
    最后是 [DONE]。
    """
    try:
        yield make_sse({"event": "conversation", "conversation_id": conversation_id})
        for event in await turns.chat_turn(request, conversation_id, runtime):
            yield event_to_sse(event)
    finally:
        yield DONE_SSE


@router.post("/graph-chat")
async def graph_chat(
    request: ChatRequest,
    http_request: Request,
    user_id: str = Depends(limit_customer_chat),
) -> StreamingResponse:
    """
    图模式聊天接口端点

    参数:
        request: ChatRequest对象
        http_request: FastAPI请求对象，用于访问app.state中的图运行时

    返回:
        StreamingResponse，media_type为text/event-stream

    核心逻辑：
    1. 从app.state获取图运行时实例
    2. 首次聊天时创建新会话
    3. 续聊时校验会话存在性
    4. 检查是否有待确认的工单
    5. 调用stream_graph_chat生成流式响应

    边界情况：
    - 图服务未启动时返回503
    - 会话不存在时返回404
    - 有待确认工单时返回409
    """
    # 身份只来自令牌，覆盖请求体里可能伪造的 user_id
    request.user_id = user_id

    # 获取图运行时实例
    runtime: Runtime | None = getattr(http_request.app.state, "graph_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="图服务未启动")

    # 首次聊天，创建新会话
    if request.conversation_id is None:
        conversation_id = await repository.create_conversation(request.user_id)
    else:
        # 续聊，校验会话存在性
        conversation = await repository.get_conversation(
            request.conversation_id,
            request.user_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        conversation_id = conversation.id

        # 检查是否有待确认的工单
        if await repository.get_pending_ticket_call(conversation_id) is not None:
            raise HTTPException(status_code=409, detail="请先确认或取消待处理工单")

    # 返回流式响应
    return StreamingResponse(
        stream_graph_chat(request, conversation_id, runtime),
        media_type="text/event-stream",
    )
