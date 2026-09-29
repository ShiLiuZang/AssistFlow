"""
聊天API路由模块

本模块实现基于工具调用的流式聊天接口，支持订单查询、知识库检索和工单创建等功能。
核心功能包括：多轮工具调用循环、会话历史管理、SSE流式响应、工单确认中断机制。
在系统中充当用户交互的主要入口，协调LLM、工具系统和数据库的交互。
"""

import json
import logging
from collections.abc import AsyncIterator
from app.db import repository
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from app.tools.engine import classify_tool_result
from app.tools.order_tools import query_order
from app.core.llm import get_chat_model
from app.core.prompts import CHAT_SYSTEM_PROMPT
from app.schemas.chat import ChatRequest
from app.tools.ticket_tools import create_ticket
from app.tools.knowledge_tools import search_knowledge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

# 单次对话中最多允许的工具调用轮次，防止无限循环
MAX_TOOL_ROUNDS = 3

# 注册到模型的所有可用工具列表
TOOL_BY_NAME = [query_order, create_ticket, search_knowledge]


def make_sse(data: dict) -> str:
    """
    将字典编码为Server-Sent Events (SSE)格式的数据帧

    参数:
        data: 要发送的数据字典

    返回:
        格式化的SSE字符串，包含"data: "前缀和双换行符结尾

    SSE协议要求每个消息以"data: "开头，以两个换行符结尾
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"data: {payload}\n\n"


def graph_event_to_sse(
    event: dict,
    conversation_id: int,
) -> str:
    """
    将图运行时事件转换为聊天SSE协议格式

    参数:
        event: 图运行时产生的事件字典
        conversation_id: 当前会话ID

    返回:
        SSE格式的事件字符串

    此函数用于兼容图模式(graph_chat.py)，将图事件映射到标准聊天事件
    处理特殊事件类型：citations转换为items，interrupt附加预览信息
    """
    if event.get("event") == "end":
        return "data: [DONE]\n\n"

    if event.get("event") == "error":
        return 'event: error\ndata: {"message":"图执行失败，请重试"}\n\n'

    payload = dict(event)
    if payload.get("event") == "citations":
        payload["items"] = payload.pop("citations", [])
    if payload.get("event") in {"done", "interrupt"}:
        payload["conversation_id"] = conversation_id

    if payload.get("event") == "interrupt":
        payload.update(payload.pop("preview"))

    return make_sse(payload)


def restored_tool_status(content: str) -> str:
    """
    从工具消息内容中恢复工具执行状态

    参数:
        content: 工具消息的JSON字符串内容

    返回:
        "success" 或 "error"

    尝试解析工具返回值并调用classify_tool_result判断成功或失败
    如果解析失败或分类结果非success，统一返回error
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

    根据消息角色构造不同类型的消息：
    - user角色转为HumanMessage
    - assistant角色转为AIMessage，包含工具调用信息
    - tool角色转为ToolMessage，自动恢复执行状态
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


async def stream_chat(
    request: ChatRequest,
    conversation_id: int,
) -> AsyncIterator[str]:
    """
    执行流式聊天的核心函数，产出SSE格式的响应流

    参数:
        request: 聊天请求对象，包含用户消息和用户ID
        conversation_id: 当前会话ID

    产出:
        SSE格式的字符串流，包括：
        - delta事件：AI回复的增量文本
        - tool事件：工具调用通知
        - interrupt事件：需要用户确认的中断（如工单创建）
        - done事件：对话完成
        - error事件：执行失败
        - [DONE]标记：流结束

    核心逻辑：
    1. 加载会话历史并恢复为消息列表
    2. 追加用户消息到数据库
    3. 进入工具调用循环（最多MAX_TOOL_ROUNDS轮）：
       - 调用模型流式生成回复
       - 如果有工具调用，逐个执行工具
       - 工单创建工具触发中断，等待用户确认
       - 将工具结果追加到消息列表
    4. 循环结束后发送done事件
    5. 任何异常统一返回error事件

    边界情况：
    - 工具调用超过最大轮次时返回提示消息
    - 每轮只允许创建一个工单（pending_interrupt机制）
    - 工具执行异常时记录日志并返回错误消息
    """
    try:
        # 获取支持工具调用的流式模型
        model = get_chat_model(streaming=True).bind_tools(TOOL_BY_NAME)

        # 从数据库加载会话历史
        records = await repository.list_messages(conversation_id)
        history = restore_messages(records)

        # 构造完整的消息列表：系统提示词 + 历史 + 新消息
        messages = [
            SystemMessage(content=CHAT_SYSTEM_PROMPT),
            *history,
            HumanMessage(content=request.message),
        ]

        # 将用户消息持久化到数据库
        await repository.append_message(
            conversation_id,
            "user",
            request.message,
        )

        # 工作消息列表，在工具调用循环中不断追加
        working_messages = list(messages)

        # 默认回答，当工具调用超限时使用
        answer = "工具调用次数过多，请稍后重试"

        # 工具调用循环
        for _ in range(MAX_TOOL_ROUNDS):
            ai_message = None

            # 流式获取模型回复，逐块产出文本内容
            async for chunk in model.astream(working_messages):
                ai_message = chunk if ai_message is None else ai_message + chunk
                if isinstance(chunk.content, str) and chunk.content:
                    yield make_sse({"delta": chunk.content})

            if ai_message is None:
                raise ValueError("模型返回空流")

            # 将完整的AI消息追加到工作列表和数据库
            working_messages.append(ai_message)
            await repository.append_message(
                conversation_id,
                "assistant",
                str(ai_message.content),
                tool_calls=ai_message.tool_calls or None,
            )

            # 如果没有工具调用，说明对话完成
            if not ai_message.tool_calls:
                answer = str(ai_message.content)
                break

            # 处理工具调用，pending_interrupt用于暂存需要确认的工单
            pending_interrupt = None
            for tool_call in ai_message.tool_calls:
                try:
                    # 订单查询工具：注入用户ID并执行
                    if tool_call["name"] == query_order.name:
                        yield make_sse({
                            "event": "tool",
                            "name": query_order.name,
                        })
                        tool_args = {
                            **tool_call["args"],
                            "user_id": request.user_id,
                        }
                        tool_result = await query_order.ainvoke(tool_args)

                    # 知识库检索工具：直接执行
                    elif tool_call["name"] == search_knowledge.name:
                        yield make_sse({"event": "tool", "name": search_knowledge.name})
                        tool_result = await search_knowledge.ainvoke(tool_call["args"])

                    # 工单创建工具：生成预览并触发中断，等待用户确认
                    elif tool_call["name"] == create_ticket.name:
                        if pending_interrupt is None:
                            preview = await create_ticket.ainvoke(
                                tool_call["args"]
                            )
                            pending_interrupt = {
                                "event": "interrupt",
                                "kind": "confirm_ticket",
                                "tool_call_id": tool_call["id"],
                                "conversation_id": conversation_id,
                                "preview": {
                                    "ticket_type": preview["ticket_type"],
                                    "description": preview["description"],
                                },
                            }
                            # 跳过后续处理，等待确认
                            continue

                        # 如果已有待确认工单，拒绝创建新工单
                        tool_result = {
                            "error": "本轮只处理一张工单，此请求未执行",
                        }

                    else:
                        tool_result = {
                            "error": "未知工具",
                        }

                except Exception:
                    logger.exception(
                        "工具执行失败 name=%s tool_call_id=%s",
                        tool_call["name"],
                        tool_call["id"],
                    )
                    tool_result = {
                        "error": "工具执行失败，请稍后重试",
                    }

                # 构造工具消息并追加到工作列表和数据库
                tool_message = ToolMessage(
                    content=json.dumps(tool_result, ensure_ascii=False),
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"],
                )
                working_messages.append(tool_message)

                await repository.append_message(
                    conversation_id,
                    "tool",
                    str(tool_message.content),
                    tool_call_id=tool_call["id"],
                )

            # 如果有待确认工单，发送中断事件并结束流
            if pending_interrupt is not None:
                yield make_sse(pending_interrupt)
                return
        else:
            # for循环正常结束（未break），说明达到最大轮次
            # 追加默认回答到数据库并产出
            await repository.append_message(conversation_id, "assistant", answer)
            yield make_sse({"delta": answer})

        # 发送对话完成事件
        yield make_sse(
            {
                "event": "done",
                "conversation_id": conversation_id,
            })

    except Exception:
        logger.exception(
            "聊天模型调用失败 conversation_id=%s",
            conversation_id,
        )
        yield (
            "event: error\n"
            'data: {"message":"模型调用失败，请稍后重试"}\n\n'
        )
    finally:
        # 无论成功或失败，都发送流结束标记
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    聊天接口端点，接收用户消息并返回流式响应

    参数:
        request: ChatRequest对象，包含message、user_id、可选的conversation_id

    返回:
        StreamingResponse，media_type为text/event-stream

    核心逻辑：
    1. 首次聊天时创建新会话（conversation_id为None）
    2. 续聊时校验会话存在性和所属权
    3. 检查是否有待确认的工单，有则拒绝新消息
    4. 调用stream_chat生成流式响应

    边界情况：
    - 会话不存在时返回404
    - 有待确认工单时返回409，提示用户先确认或取消
    """
    # 首次聊天，创建新会话
    if request.conversation_id is None:
        conversation_id = await repository.create_conversation(
            request.user_id
        )
    else:
        # 续聊，校验会话存在性
        conversation = await repository.get_conversation(
            request.conversation_id,
            request.user_id,
        )

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="会话不存在",
            )

        conversation_id = conversation.id

        # 检查是否有待确认的工单，有则阻塞新消息
        if await repository.get_pending_ticket_call(conversation_id) is not None:
            raise HTTPException(status_code=409, detail="请先确认或取消待处理工单")

    # 返回流式响应
    return StreamingResponse(
        stream_chat(request, conversation_id),
        media_type="text/event-stream",
    )
