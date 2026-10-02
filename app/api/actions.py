"""
用户操作确认API路由模块

本模块处理需要用户确认的操作，包括工单创建确认和订单选择。
核心功能包括：工单确认/取消、订单选择、待处理操作查询、图状态恢复。
在系统中充当人机协作的关键节点，确保关键操作经过用户明确授权后执行。
与chat.py的关系：chat.py触发中断，本模块处理中断后的恢复。
"""

import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.core.observability import span
from app.schemas.actions import ResumeTicketRequest, SelectOrderRequest
from app.api.sse import make_sse, graph_event_to_sse
from app.api.graph_chat import _thread_config, _persist_graph_messages
from app.core.conversation_lock import conversation_lock
from app.db import repository
from app.graph.runtime import Runtime
from app.core.summarizer import schedule_persisted_summary, summarize_dialog
from app.tools.audit import (
    build_ticket_decision_audit,
    emit_tool_audit,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/actions", tags=["actions"])


def _interrupt(snapshot):
    """
    从图快照中提取当前中断信息

    参数:
        snapshot: LangGraph状态快照

    返回:
        中断对象（如果有），否则返回None

    遍历所有任务的中断列表，返回第一个中断
    """
    return next((item.value for task in snapshot.tasks for item in task.interrupts), None)


def _call_in_current_turn(snapshot, call_id: str) -> bool:
    """
    判断指定工具调用是否在当前轮次中

    参数:
        snapshot: 图状态快照
        call_id: 工具调用ID

    返回:
        True如果调用在当前轮次，False否则

    从最新消息向前遍历，遇到human消息（轮次边界）就停止
    如果在此之前找到匹配的tool_call，说明在当前轮次
    """
    for message in reversed(snapshot.values.get("messages", [])):
        if message.type == "human":
            return False
        if any(call["id"] == call_id for call in getattr(message, "tool_calls", [])):
            return True
    return False


async def stream_ticket_decision(
    request: ResumeTicketRequest, tool_call: dict, runtime: Runtime | None = None,
) -> AsyncIterator[str]:
    """
    处理工单确认/取消的核心函数

    参数:
        request: 工单确认请求，包含confirmed字段
        tool_call: 原始的create_ticket工具调用
        runtime: 图运行时（可选，非图模式为None）

    产出:
        SSE格式的事件流

    核心逻辑：
    1. 获取会话锁和图快照
    2. 校验当前中断与请求是否匹配
    3. 调用repository.decide_ticket保存决策并执行（确认时创建工单）
    4. 生成审计记录
    5. 如果是图模式：
       - 有待处理中断：恢复图执行
       - 图状态未完成且调用在当前轮次：继续执行图
       - 其他情况：使用当前图状态
    6. 持久化图消息
    7. 如果有新中断，产出interrupt事件；否则产出done事件
    8. 如果图轮次完成，调度摘要任务

    边界情况：
    - 中断不匹配时抛出异常
    - 非图模式也支持工单确认（兼容旧chat.py）
    - 已保存决策时允许重新确认（幂等）

    为什么需要会话锁：
    工单决策会修改数据库和图状态，必须串行化
    """
    try:
        # 使用trace span追踪整个操作，并获取会话锁
        async with (
            span("ticket_action", repository.insert_trace_span),
            conversation_lock(request.user_id, request.conversation_id),
        ):
            call_id = str(tool_call["id"])
            graph_result = None
            snapshot = None
            pending = None

            # 如果有图运行时，获取当前快照和中断
            if runtime is not None:
                snapshot = await runtime.graph.aget_state(
                    _thread_config(request.user_id, request.conversation_id),
                )
                pending = _interrupt(snapshot)

            # 查询是否已有保存的决策
            saved = await repository.get_ticket_decision(request.conversation_id, call_id)

            # 校验中断匹配性
            if pending and pending.get("tool_call_id") != call_id and saved is None:
                raise ValueError("确认调用与当前中断不匹配")

            is_graph = bool(snapshot and snapshot.values)

            # 图模式下，如果没有保存决策也没有待处理中断，说明状态异常
            if is_graph and saved is None and not pending:
                raise ValueError("没有待恢复的工单中断")

            # 执行工单决策（保存到数据库，确认时创建工单）
            async with span(
                "ticket_decision",
                repository.insert_trace_span,
            ):
                started = time.monotonic()
                result = await repository.decide_ticket(
                    request.conversation_id,
                    request.user_id,
                    call_id,
                    request.confirmed,
                    graph=is_graph,
                )
                duration_ms = int((time.monotonic() - started) * 1000)

            # 生成审计记录
            try:
                audit_record = build_ticket_decision_audit(
                    tool_call,
                    request.conversation_id,
                    result,
                    duration_ms,
                )
            except Exception as error:
                logger.warning(
                    "工单审计记录构造失败：error_type=%s",
                    type(error).__name__,
                )
            else:
                await emit_tool_audit(
                    repository.insert_tool_audit,
                    audit_record,
                )

            # 图模式下的后续处理
            if pending and pending.get("tool_call_id") == call_id:
                # 有待处理中断，恢复图执行
                graph_result = await runtime.run_turn(
                    "", request.user_id, str(request.conversation_id),
                    resume={"tool_call_id": call_id, "tool_result": result},
                )
            elif is_graph and snapshot.next and not pending and _call_in_current_turn(snapshot, call_id):
                # 图状态未完成且调用在当前轮次，继续执行图
                async with span(
                    "graph_turn",
                    repository.insert_trace_span,
                ):
                    graph_result = await runtime.graph.ainvoke(
                        None,
                        _thread_config(
                            request.user_id,
                            request.conversation_id,
                        ),
                    )
            elif is_graph:
                # 其他情况，使用当前图状态
                graph_result = dict(snapshot.values)
                if pending:
                    graph_result["__interrupt__"] = [
                        item for task in snapshot.tasks for item in task.interrupts
                    ]

            # 持久化图消息
            if is_graph:
                await _persist_graph_messages(runtime, request.user_id, request.conversation_id)

            # 检查是否有新中断
            interrupts = graph_result.get("__interrupt__") if graph_result else None
            frames = []

            if interrupts:
                # 有新中断，产出interrupt事件
                frames.append(graph_event_to_sse(
                    {"event": "interrupt", "preview": interrupts[0].value},
                    request.conversation_id,
                ))
            else:
                # 无中断，产出答案和done事件
                frames.append(make_sse({"delta": repository.ticket_answer(result)}))
                frames.append(make_sse({"event": "done", "conversation_id": request.conversation_id}))

            # 判断图轮次是否完成
            completed_graph_turn = False
            if is_graph and not interrupts:
                latest = await runtime.graph.aget_state(
                    _thread_config(request.user_id, request.conversation_id)
                )
                completed_graph_turn = not latest.next

        # 如果图轮次完成，调度摘要任务
        if completed_graph_turn:
            schedule_persisted_summary(
                request.user_id,
                request.conversation_id,
                summarize_dialog,
            )

        # 产出所有事件帧
        for frame in frames:
            yield frame

    except Exception:
        logger.exception("处理工单确认失败 conversation_id=%s", request.conversation_id)
        yield 'event: error\ndata: {"message":"工单处理或图恢复失败，请重试同一确认请求"}\n\n'
    finally:
        yield "data: [DONE]\n\n"


async def stream_order_selection(
    request: SelectOrderRequest,
    runtime: Runtime,
) -> AsyncIterator[str]:
    """
    处理订单选择的核心函数

    参数:
        request: 订单选择请求，包含order_id或cancelled标志
        runtime: 图运行时

    产出:
        SSE格式的事件流

    核心逻辑：
    1. 获取会话锁
    2. 构造恢复参数（包含kind、request_id、order_id、cancelled）
    3. 调用runtime.stream_turn恢复图执行
    4. 持久化图消息
    5. 如果对话正常完成，调度摘要任务
    6. 产出所有图事件

    订单选择中断由图节点触发，当查询到多个订单时需要用户澄清
    """
    try:
        async with conversation_lock(
            request.user_id,
            request.conversation_id,
        ):
            # 构造恢复参数
            resume = request.model_dump(
                include={"kind", "request_id", "order_id", "cancelled"},
                exclude_none=True,
            )

            # 恢复图执行
            events = [
                event
                async for event in runtime.stream_turn(
                    "",
                    request.user_id,
                    str(request.conversation_id),
                    resume=resume,
                )
            ]

            # 持久化图消息
            await _persist_graph_messages(
                runtime,
                request.user_id,
                request.conversation_id,
            )

        # 判断对话是否成功完成
        completed = any(e.get("event") == "done" for e in events)
        interrupted_or_failed = any(
            e.get("event") in {"interrupt", "error"} for e in events
        )

        # 如果对话正常完成，调度摘要任务
        if completed and not interrupted_or_failed:
            schedule_persisted_summary(
                request.user_id,
                request.conversation_id,
                summarize_dialog,
            )

        # 产出所有事件（跳过end事件）
        for event in events:
            if event.get("event") != "end":
                yield graph_event_to_sse(
                    event,
                    request.conversation_id,
                )

    except Exception:
        logger.exception(
            "订单选择或消息保存失败 conversation_id=%s",
            request.conversation_id,
        )
        yield make_sse({
            "event": "error",
            "message": "订单选择或消息保存失败，请检查当前待处理状态",
        })
    finally:
        yield "data: [DONE]\n\n"


@router.get("/pending")
async def pending_ticket(conversation_id: int, user_id: str, http_request: Request):
    """
    查询指定会话的待处理操作

    参数:
        conversation_id: 会话ID
        user_id: 用户ID
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
            snapshot = await runtime.graph.aget_state(_thread_config(user_id, conversation_id))
            pending = _interrupt(snapshot)

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
async def resume_ticket(request: ResumeTicketRequest, http_request: Request) -> StreamingResponse:
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
    # 校验会话存在性
    conversation = await repository.get_conversation(request.conversation_id, request.user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 获取图运行时
    runtime = getattr(http_request.app.state, "graph_runtime", None)
    call_id = request.tool_call_id

    # 图模式下要求携带tool_call_id
    if runtime is not None:
        snapshot = await runtime.graph.aget_state(_thread_config(request.user_id, request.conversation_id))
        if snapshot.values and call_id is None:
            raise HTTPException(status_code=409, detail="图确认必须携带工具调用 ID")

    # 如果未携带tool_call_id，从数据库查询
    if call_id is None:
        pending = await repository.get_pending_ticket_call(request.conversation_id)
        if pending is None:
            raise HTTPException(status_code=409, detail="没有待确认的工单")
        call_id = str(pending["id"])

    # 从消息历史中查找对应的工具调用
    records = await repository.list_messages(request.conversation_id)
    tool_call = next((call for record in reversed(records) for call in record.tool_calls or []
                      if call.get("id") == call_id and call.get("name") == "create_ticket"), None)
    if tool_call is None:
        raise HTTPException(status_code=409, detail="没有对应的工单调用")

    # 返回流式响应
    return StreamingResponse(stream_ticket_decision(request, tool_call, runtime),
                             media_type="text/event-stream")


@router.post("/select-order")
async def select_order(
    request: SelectOrderRequest,
    http_request: Request,
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
