"""
用户操作确认API路由模块

本模块处理需要用户确认的操作，包括工单创建确认和订单选择。
核心功能包括：工单确认/取消、订单选择、待处理操作查询、图状态恢复。
在系统中充当人机协作的关键节点，确保关键操作经过用户明确授权后执行。
与chat.py的关系：chat.py触发中断，本模块处理中断后的恢复。
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.core.auth import current_customer
from app.core.ratelimit import limit_customer_chat
from app.schemas.actions import ResumeTicketRequest, SelectOrderRequest
from app.api.sse import DONE_SSE, event_to_sse
from app.core.conversation_lock import conversation_lock
from app.db import repository
from app.graph import turns
from app.graph.runtime import Runtime

router = APIRouter(prefix="/api/actions", tags=["actions"])


async def stream_ticket_decision(
    request: ResumeTicketRequest, tool_call: dict, runtime: Runtime | None = None,
) -> AsyncIterator[str]:
    """工单确认或取消（turns.ticket_decision_turn），编码成 SSE。"""
    try:
        for event in await turns.ticket_decision_turn(request, tool_call, runtime):
            yield event_to_sse(event)
    finally:
        yield DONE_SSE


async def stream_order_selection(request: SelectOrderRequest, runtime: Runtime) -> AsyncIterator[str]:
    """订单选择（turns.order_selection_turn），编码成 SSE。"""
    try:
        for event in await turns.order_selection_turn(request, runtime):
            yield event_to_sse(event)
    finally:
        yield DONE_SSE


@router.get("/pending")
async def pending_ticket(
    conversation_id: int,
    http_request: Request,
    user_id: str = Depends(current_customer),
):
    """
    查询指定会话的待处理操作

    参数:
        conversation_id: 会话ID
        user_id: 令牌中的顾客 ID
        http_request: FastAPI请求对象

    返回:
        待处理操作对象，包含kind、tool_call_id、preview等字段；无待处理操作时返回None

    核心逻辑：
    1. 校验会话存在性
    2. 获取会话锁
    3. 如果有图运行时，从图快照中提取中断
    4. 如果是订单选择中断，直接返回
    5. 如果是工单中断，查询是否已有保存的决策
    6. 如果图中无中断，查询数据库中的待确认工单

    为什么需要会话锁：
    避免在查询待处理操作时，其他请求修改图状态
    """
    # 校验会话存在性
    if await repository.get_conversation(conversation_id, user_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    async with conversation_lock(user_id, conversation_id):
        # 尝试从图快照中提取中断
        runtime = getattr(http_request.app.state, "graph_runtime", None)
        if runtime is not None:
            snapshot = await runtime.graph.aget_state(turns.thread_config(user_id, conversation_id))
            pending = turns.snapshot_interrupt(snapshot)

            # 订单选择中断
            if pending and pending.get("kind") == "select_order":
                return {
                    **pending,
                    "conversation_id": conversation_id,
                }

            # 工单确认中断
            if pending:
                saved = await repository.get_ticket_decision(conversation_id, pending["tool_call_id"])
                return {**pending, "conversation_id": conversation_id,
                        "confirmed": saved["confirmed"] if saved else None}

        # 图中无中断，查询数据库中的待确认工单
        call = await repository.get_pending_ticket_call(conversation_id)
        if call is None:
            return None

        saved = await repository.get_ticket_decision(conversation_id, call["id"])
        return {"kind": "confirm_ticket", "conversation_id": conversation_id,
                "tool_call_id": call["id"], "preview": call["args"],
                "confirmed": saved["confirmed"] if saved else None}


@router.post("/resume")
async def resume_ticket(
    request: ResumeTicketRequest,
    http_request: Request,
    user_id: str = Depends(limit_customer_chat),
) -> StreamingResponse:
    """
    恢复工单确认流程

    参数:
        request: ResumeTicketRequest对象
        http_request: FastAPI请求对象

    返回:
        StreamingResponse，media_type为text/event-stream

    核心逻辑：
    1. 校验会话存在性
    2. 如果有图运行时且图状态非空，要求携带tool_call_id
    3. 如果未携带tool_call_id，从数据库查询待确认工单
    4. 从消息历史中查找对应的create_ticket调用
    5. 调用stream_ticket_decision处理确认

    边界情况：
    - 会话不存在时返回404
    - 图模式下缺少tool_call_id时返回409
    - 无待确认工单时返回409
    - 找不到对应工具调用时返回409
    """
    # 身份只来自令牌
    request.user_id = user_id

    # 校验会话存在性
    conversation = await repository.get_conversation(request.conversation_id, request.user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 获取图运行时
    runtime = getattr(http_request.app.state, "graph_runtime", None)
    call_id = request.tool_call_id

    # 图模式下要求携带tool_call_id
    if runtime is not None:
        snapshot = await runtime.graph.aget_state(turns.thread_config(request.user_id, request.conversation_id))
        if snapshot.values and call_id is None:
            raise HTTPException(status_code=409, detail="图确认必须携带工具调用 ID")

    # 如果未携带tool_call_id，从数据库查询
    if call_id is None:
        pending = await repository.get_pending_ticket_call(request.conversation_id)
        if pending is None:
            raise HTTPException(status_code=409, detail="没有待确认的工单")
        call_id = str(pending["id"])

    # 从消息历史中查找对应的工具调用
    tool_call = await turns.find_ticket_call(request.conversation_id, call_id)
    if tool_call is None:
        raise HTTPException(status_code=409, detail="没有对应的工单调用")

    # 返回流式响应
    return StreamingResponse(stream_ticket_decision(request, tool_call, runtime),
                             media_type="text/event-stream")


@router.post("/select-order")
async def select_order(
    request: SelectOrderRequest,
    http_request: Request,
    user_id: str = Depends(limit_customer_chat),
) -> StreamingResponse:
    """
    处理订单选择

    参数:
        request: SelectOrderRequest对象
        http_request: FastAPI请求对象

    返回:
        StreamingResponse，media_type为text/event-stream

    核心逻辑：
    1. 校验会话存在性
    2. 校验图服务是否启动
    3. 调用stream_order_selection处理选择

    边界情况：
    - 会话不存在时返回404
    - 图服务未启动时返回503
    """
    # 身份只来自令牌
    request.user_id = user_id

    # 校验会话存在性
    conversation = await repository.get_conversation(
        request.conversation_id,
        request.user_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 校验图服务是否启动
    runtime = getattr(
        http_request.app.state,
        "graph_runtime",
        None,
    )
    if runtime is None:
        raise HTTPException(status_code=503, detail="图服务尚未就绪")

    # 返回流式响应
    return StreamingResponse(
        stream_order_selection(request, runtime),
        media_type="text/event-stream",
    )
