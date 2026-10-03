"""
图模式聊天API路由模块

本模块实现基于LangGraph的状态图聊天接口，支持复杂的多步推理和状态管理。
核心功能包括：图状态持久化、会话历史同步、对话摘要调度、消息一致性校验。
在系统中充当高级对话管理器，适用于需要多轮规划、工具编排和上下文压缩的场景。
与chat.py的区别：使用图运行时管理状态，支持断点续传和自动摘要。
"""

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.sse import TURN_TIMEOUT_SSE, collect_turn, graph_event_to_sse, restore_messages, make_sse
from app.core import handoff
from app.core.summarizer import schedule_persisted_summary, summarize_dialog
from app.db import repository
from app.core.conversation_lock import conversation_lock
from app.graph.runtime import Runtime
from app.core.ratelimit import limit_customer_chat
from app.schemas.chat import ChatRequest


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["graph-chat"])


def _thread_config(user_id: str, conversation_id: int) -> dict:
    """
    生成LangGraph线程配置字典

    参数:
        user_id: 用户标识
        conversation_id: 会话ID

    返回:
        包含thread_id的配置字典，用于图状态的持久化和恢复

    thread_id格式为"用户ID:会话ID"，确保每个会话有独立的图状态
    """
    return {
        "configurable": {
            "thread_id": f"{user_id}:{conversation_id}",
        },
    }


async def _persist_graph_messages(
    runtime: Runtime, user_id: str, conversation_id: int,
) -> None:
    """
    将图运行时的消息持久化到数据库

    参数:
        runtime: 图运行时实例
        user_id: 用户标识
        conversation_id: 会话ID

    从图快照中提取消息列表，调用repository持久化到数据库
    这是图状态与数据库的同步点，确保消息不会因图重启而丢失
    """
    snapshot = await runtime.graph.aget_state(_thread_config(user_id, conversation_id))
    await repository.persist_graph_messages(
        conversation_id, user_id, snapshot.values.get("messages", []),
    )


async def stream_graph_chat(
    request: ChatRequest, conversation_id: int, runtime: Runtime,
) -> AsyncIterator[str]:
    """
    执行图模式流式聊天的核心函数

    参数:
        request: 聊天请求对象
        conversation_id: 会话ID
        runtime: 图运行时实例

    产出:
        SSE格式的事件流，包括conversation、delta、tool、citations、done、interrupt、error等事件

    核心逻辑：
    1. 获取会话锁，防止并发修改图状态
    2. 从图快照或数据库恢复消息历史
    3. 计算已摘要的消息数量（covered_count）
    4. 如果图状态为空但有历史消息，初始化图状态
    5. 调用runtime.stream_turn执行图运行并收集事件
    6. 持久化图消息到数据库
    7. 如果对话正常完成（无中断或错误），调度摘要任务
    8. 逐个产出事件（转换为SSE格式）

    为什么使用会话锁：
    图状态是有状态的，并发请求可能导致状态不一致

    边界情况：
    - 会话不存在时抛出异常
    - 图消息与数据库消息不一致时由count_covered_messages检测
    - 任何异常统一返回error事件
    """
    try:
        # 首先发送会话ID，让客户端知道当前会话
        yield make_sse({"event": "conversation", "conversation_id": conversation_id})

        # 获取会话锁，防止并发修改图状态
        async with conversation_lock(request.user_id, conversation_id):
            # 排队或人工接待中：消息直接交给坐席，不经过 AI
            routed = await handoff.customer_message(conversation_id, request.user_id, request.message)
            if routed is not None:
                yield make_sse({"event": "handoff", "conversation_id": conversation_id, **routed})
                yield make_sse({"event": "done", "conversation_id": conversation_id, "message_id": None,
                                "handoff": True})
                return

            config = _thread_config(request.user_id, conversation_id)

            # 获取图当前快照
            snapshot = await runtime.graph.aget_state(config)

            # 获取会话元数据（包含摘要信息）
            conversation = await repository.get_conversation(conversation_id, request.user_id)
            if conversation is None:
                raise ValueError("会话不存在")

            # 从数据库加载消息历史
            records = await repository.list_messages(conversation_id)

            # 决定使用数据库历史还是图状态中的消息
            # 如果图状态为空，使用数据库恢复；否则使用图状态（图是真实来源）
            graph_messages = (
                restore_messages(records)
                if not snapshot.values
                else snapshot.values.get("messages", [])
            )

            # 计算已被摘要覆盖的消息数量
            covered_count = count_covered_messages(
                records, graph_messages, conversation.summary_upto or 0,
            )

            # 如果图状态为空但有历史消息，初始化图状态
            # as_node="finish"表示这些消息已经处理完成
            if not snapshot.values and graph_messages:
                await runtime.graph.aupdate_state(
                    config, {"messages": graph_messages}, as_node="finish",
                )

            # 执行图运行，收集所有事件
            events = await collect_turn(runtime.stream_turn(
                request.message,
                request.user_id,
                str(conversation_id),
                summary_text=conversation.summary_text or "",
                summary_upto=conversation.summary_upto or 0,
                covered_count=covered_count,
            ))

            # 将图消息持久化到数据库
            await _persist_graph_messages(runtime, request.user_id, conversation_id)

        # 判断对话是否成功完成（没有中断或错误）
        completed = any(e.get("event") == "done" for e in events)
        interrupted_or_failed = any(
            e.get("event") in {"interrupt", "error"} for e in events
        )

        # 如果对话正常完成，调度后台摘要任务
        if completed and not interrupted_or_failed:
            schedule_persisted_summary(
                request.user_id,
                conversation_id,
                summarize_dialog,
            )

        # 本轮转入了人工排队（human / complaint 节点），先告诉前端接待状态
        try:
            state = await handoff.open_status(conversation_id)
        except Exception:
            logger.warning("读取人工接待状态失败 conversation_id=%s", conversation_id, exc_info=True)
            state = None
        if state is not None:
            yield make_sse({"event": "handoff", "conversation_id": conversation_id, "handoff": state})

        # 产出所有事件（跳过end事件，转换为SSE格式）
        for event in events:
            if event.get("event") != "end":
                yield graph_event_to_sse(event, conversation_id)

    except TimeoutError:
        logger.warning("图聊天超时 conversation_id=%s", conversation_id)
        yield TURN_TIMEOUT_SSE
    except Exception:
        logger.exception("图聊天失败 conversation_id=%s", conversation_id)
        yield 'event: error\ndata: {"message":"图执行或消息保存失败，请重试"}\n\n'
    finally:
        # 无论成功或失败，都发送流结束标记
        yield "data: [DONE]\n\n"


def count_covered_messages(records, graph_messages, summary_upto: int) -> int:
    """
    计算已被摘要覆盖的消息数量，并校验图消息与数据库消息的一致性

    参数:
        records: 数据库消息记录列表
        graph_messages: 图状态中的消息列表
        summary_upto: 摘要游标，指向最后一条被摘要的消息ID

    返回:
        已被摘要覆盖的消息数量

    核心逻辑：
    1. 过滤出有效角色的消息（user、assistant、tool）
    2. 校验数据库历史不能比图历史长（图是真实来源）
    3. 逐条比对消息的类型、内容、工具调用、tool_call_id
    4. 校验摘要游标指向的是有效消息
    5. 统计ID小于等于摘要游标的消息数量

    为什么需要这个函数：
    图状态和数据库可能因异常或并发而不一致，必须在使用前校验
    covered_count用于告诉图哪些消息已被压缩，可以从上下文中移除
    """
    # 角色映射：数据库角色 -> 图消息类型
    roles = {"user": "human", "assistant": "ai", "tool": "tool"}

    # 过滤出有效角色的消息
    rows = [row for row in records if row.role in roles]

    # 数据库历史不能比图历史长
    if len(rows) > len(graph_messages):
        raise ValueError("数据库历史比图历史长")

    # 逐条比对消息一致性
    for row, message in zip(rows, graph_messages):
        if (
            message.type != roles[row.role]
            or str(message.content) != (row.content or "")
            or (getattr(message, "tool_calls", None) or []) != (row.tool_calls or [])
            or getattr(message, "tool_call_id", None) != row.tool_call_id
        ):
            raise ValueError(f"图消息与数据库消息不一致：{row.id}")

    # 校验摘要游标有效性
    if summary_upto and not any(row.id == summary_upto for row in rows):
        raise ValueError("摘要游标未指向一条模型消息")

    # 统计已被摘要覆盖的消息数量
    return sum(row.id <= summary_upto for row in rows)


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
