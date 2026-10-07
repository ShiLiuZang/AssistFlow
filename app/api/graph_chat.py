"""
图模式聊天API路由模块

本模块实现基于LangGraph的状态图聊天接口，是系统唯一的聊天入口。
核心功能包括：图状态持久化、会话历史同步、对话摘要调度、消息一致性校验。
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from app.core.auth import require_visitor, resolve_visitor_id

from fastapi import Depends, APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.api.sse import graph_event_to_sse, make_sse
from app.core.summarizer import schedule_persisted_summary, summarize_dialog
from app.db import conversation_repo
from app.core.conversation_lock import conversation_lock
from app.graph.runtime import Runtime
from app.schemas.chat import ChatRequest
from app.tools.engine import classify_tool_result


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["graph-chat"])
_stream_tasks: set[asyncio.Task] = set()


def restored_tool_status(content: str) -> str:
    """
    从工具消息内容中恢复工具执行状态

    参数:
        content: 工具消息的JSON字符串内容

    返回:
        "success" 或 "error"
    """
    try:
        result = json.loads(content)
    except (TypeError, ValueError):
        return "error"

    status = classify_tool_result(result)
    return "success" if status == "success" else "error"


def restore_messages(records: list) -> list:
    """
    将数据库消息记录恢复为LangChain消息对象列表

    参数:
        records: 数据库中的消息记录列表，每条记录包含role、content、tool_calls等字段

    返回:
        LangChain消息对象列表（HumanMessage、AIMessage、ToolMessage）
    """
    messages = []

    for record in records:
        if record.role == "user":
            messages.append(HumanMessage(content=record.content or ""))
        elif record.role == "assistant":
            messages.append(
                AIMessage(
                    content=record.content or "",
                    tool_calls=record.tool_calls or [],
                    id=record.turn_message_id,
                )
            )
        elif record.role == "tool":
            content = record.content or ""
            messages.append(
                ToolMessage(
                    content=content,
                    tool_call_id=record.tool_call_id or "",
                    status=restored_tool_status(content),
                )
            )
    return messages


async def _persist_graph_messages(
    runtime: Runtime, user_id: str, conversation_id: int,
) -> None:
    """
    将图运行时的消息持久化到数据库

    参数:
        runtime: 图运行时实例
        user_id: 用户标识
        conversation_id: 会话ID

    从图快照中提取消息列表，调用conversation_repo持久化到数据库
    这是图状态与数据库的同步点，确保消息不会因图重启而丢失
    """
    snapshot = await runtime.get_state(user_id, conversation_id)
    await conversation_repo.persist_graph_messages(
        conversation_id, user_id, snapshot.values.get("messages", []),
    )


def schedule_graph_summary(user_id: str, conversation_id: int) -> None:
    """为已正常完成并持久化的图轮次调度后台摘要。"""
    schedule_persisted_summary(user_id, conversation_id, summarize_dialog)


async def stream_graph_events(
    runtime: Runtime, user_id: str, conversation_id: int, events: AsyncIterator[dict],
) -> AsyncIterator[str]:
    """后台任务持锁执行图并保存消息；队列实时交付 SSE，断连不取消任务。

    done/interrupt/error 在保存后交付，避免保存失败仍报告成功；end 由外层
    聊天/选单生成器映射为唯一的 [DONE]。后台任务异常交给外层编码错误帧。
    """
    queue: asyncio.Queue[dict | Exception | None] = asyncio.Queue()

    async def produce():
        try:
            terminal = []
            async with conversation_lock(user_id, conversation_id):
                async for event in events:
                    kind = event.get("event")
                    if kind in {"done", "interrupt", "error"}:
                        terminal.append(event)
                    elif kind != "end":
                        queue.put_nowait(event)
                await _persist_graph_messages(runtime, user_id, conversation_id)

            completed = any(event.get("event") == "done" for event in terminal)
            interrupted_or_failed = any(
                event.get("event") in {"interrupt", "error"} for event in terminal
            )
            if completed and not interrupted_or_failed:
                schedule_graph_summary(user_id, conversation_id)
            for event in terminal:
                queue.put_nowait(event)
        except Exception as error:
            logger.exception("图执行或消息保存失败 conversation_id=%s", conversation_id)
            queue.put_nowait(error)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(produce())
    _stream_tasks.add(task)
    task.add_done_callback(_stream_tasks.discard)
    while True:
        event = await queue.get()
        if event is None:
            break
        if isinstance(event, Exception):
            raise event
        yield graph_event_to_sse(event, conversation_id)


async def _chat_events(
    request: ChatRequest, conversation_id: int, runtime: Runtime,
) -> AsyncIterator[dict]:
    """在共享收尾函数持有的会话锁内恢复历史并执行聊天轮次。"""
    snapshot = await runtime.get_state(request.user_id, conversation_id)
    conversation = await conversation_repo.get_conversation(conversation_id, request.user_id)
    if conversation is None:
        raise ValueError("会话不存在")

    records = await conversation_repo.list_messages(conversation_id)
    graph_messages = (
        restore_messages(records)
        if not snapshot.values
        else snapshot.values.get("messages", [])
    )
    covered_count = count_covered_messages(
        records, graph_messages, conversation.summary_upto or 0,
    )
    if not snapshot.values and graph_messages:
        await runtime.seed_messages(request.user_id, conversation_id, graph_messages)

    async for event in runtime.stream_turn(
        request.message,
        request.user_id,
        str(conversation_id),
        summary_text=conversation.summary_text or "",
        summary_upto=conversation.summary_upto or 0,
        covered_count=covered_count,
    ):
        yield event


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
    5. 后台任务调用runtime.stream_turn执行图，队列实时转发事件
    6. 持久化图消息到数据库
    7. 如果对话正常完成（无中断或错误），调度摘要任务
    8. 保存成功后交付终结事件（转换为SSE格式）

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

        async for frame in stream_graph_events(
            runtime, request.user_id, conversation_id,
            _chat_events(request, conversation_id, runtime),
        ):
            yield frame

    except Exception:
        logger.exception("图聊天失败 conversation_id=%s", conversation_id)
        yield 'event: error\ndata: {"message":"图执行或消息保存失败，请重试"}\n\n'
    # 消费者关闭时不能在 GeneratorExit 的 finally 中 yield；连接存活时必达。
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
    visitor_id: str = Depends(require_visitor),
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
    4. 从图状态检查是否有待处理的工单确认或订单选择中断
    5. 调用stream_graph_chat生成流式响应

    边界情况：
    - 图服务未启动时返回503
    - 会话不存在时返回404
    - 有待处理中断时返回409
    """
    request.user_id = resolve_visitor_id(visitor_id, request.user_id)
    # 获取图运行时实例
    runtime: Runtime | None = getattr(http_request.app.state, "graph_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="图服务未启动")

    # 首次聊天，创建新会话
    if request.conversation_id is None:
        conversation_id = await conversation_repo.create_conversation(request.user_id)
    else:
        # 续聊，校验会话存在性
        conversation = await conversation_repo.get_conversation(
            request.conversation_id,
            request.user_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        conversation_id = conversation.id

        # 图中断是待处理状态的来源，不从数据库消息推断。
        pending = await runtime.pending_interrupt(request.user_id, conversation_id)
        if pending is not None:
            detail = (
                "请先选择或取消待处理订单"
                if pending.get("kind") == "select_order"
                else "请先确认或取消待处理工单"
            )
            raise HTTPException(status_code=409, detail=detail)

    # 返回流式响应
    return StreamingResponse(
        stream_graph_chat(request, conversation_id, runtime),
        media_type="text/event-stream",
    )
