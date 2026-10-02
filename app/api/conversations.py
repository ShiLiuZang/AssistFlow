"""
会话管理API路由模块

本模块提供会话列表和消息历史的查询接口，以及顾客侧的人工客服接口：
查询接待状态、转人工、取消排队、订阅坐席回复（SSE）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core import handoff
from app.core.auth import current_customer
from app.core.ratelimit import limit_customer_chat
from app.core.realtime import conversation_channel, hub
from app.db import repository

logger = logging.getLogger(__name__)


router = APIRouter(tags=["conversations"])

# 顾客页面看到的角色：人工期间的顾客消息仍显示为 user，坐席回复为 staff，接入提示为 system
CUSTOMER_ROLES = {"handoff_user": "user", "handoff_event": "system"}


@router.get("/api/conversations")
async def list_conversations(user_id: str = Depends(current_customer)) -> list[dict]:
    """
    获取指定用户的所有会话列表

    参数:
        user_id: 令牌中的顾客 ID

    返回:
        会话列表，每个会话包含id和created_at字段

    返回格式为字典列表，便于前端展示会话卡片
    """
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
    user_id: str = Depends(current_customer),
) -> list[dict]:
    """
    获取指定会话的消息历史

    参数:
        conversation_id: 会话ID（路径参数）
        user_id: 令牌中的顾客 ID（用于权限校验）

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
    conversation = await repository.get_conversation(
        conversation_id,
        user_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在",
        )

    # 查询对话消息（不包括tool角色）
    messages = await repository.list_dialog_messages(conversation_id)

    return [
        {
            "role": CUSTOMER_ROLES.get(item.role, item.role),
            "content": item.content,
            "message_id": item.turn_message_id,
        }
        for item in messages
    ]


# ==================== 人工客服 ====================

def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, "会话不存在")
    if isinstance(exc, handoff.HandoffError):
        return HTTPException(409, str(exc))
    logger.exception("人工客服接口失败")
    return HTTPException(503, "人工客服暂时不可用，请稍后再试")


@router.get("/api/conversations/{conversation_id}/handoff")
async def handoff_status(conversation_id: int, user_id: str = Depends(current_customer)) -> dict:
    """当前人工接待状态；status 为 ai 表示由智能助手接待。"""
    try:
        state = await handoff.customer_status(conversation_id, user_id)
    except Exception as exc:
        raise _not_found(exc) from exc
    return state or {"status": "ai"}


@router.post("/api/conversations/{conversation_id}/handoff")
async def request_handoff(
    conversation_id: int, request: Request, user_id: str = Depends(limit_customer_chat),
) -> dict:
    """顾客点击「转人工」。已在排队或人工接待中时直接返回当前状态。"""
    values = None
    runtime = getattr(request.app.state, "graph_runtime", None)
    if runtime is not None:
        try:
            snapshot = await runtime.graph.aget_state({"configurable": {"thread_id": f"{user_id}:{conversation_id}"}})
            values = dict(snapshot.values or {})
        except Exception:
            logger.warning("读取图状态失败 conversation_id=%s", conversation_id, exc_info=True)
    try:
        return await handoff.request(conversation_id, user_id, "customer_request", values=values)
    except Exception as exc:
        raise _not_found(exc) from exc


@router.post("/api/conversations/{conversation_id}/handoff/cancel")
async def cancel_handoff(conversation_id: int, user_id: str = Depends(current_customer)) -> dict:
    try:
        return await handoff.cancel(conversation_id, user_id)
    except Exception as exc:
        raise _not_found(exc) from exc


@router.get("/api/conversations/{conversation_id}/events")
async def conversation_events(conversation_id: int, user_id: str = Depends(current_customer)) -> StreamingResponse:
    """SSE：推送坐席回复与接待状态变化。只在单实例内有效（阶段 4 换 Redis）。"""
    if await repository.get_conversation(conversation_id, user_id) is None:
        raise HTTPException(404, "会话不存在")
    return StreamingResponse(
        hub.stream(conversation_channel(conversation_id)), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
