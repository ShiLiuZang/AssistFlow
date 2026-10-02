"""
聊天事件流的公共工具：SSE 编码、图事件转换、从数据库记录恢复 LangChain 消息。

供 graph_chat 与 actions 共用。
"""

import asyncio
import json
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.config import settings
from app.tools.engine import classify_tool_result

# 一轮对话超时后发给前端的错误帧
TURN_TIMEOUT_SSE = 'event: error\ndata: {"message":"当前咨询较多，请稍后重试或转人工"}\n\n'


async def collect_turn(events: AsyncIterator[dict]) -> list[dict]:
    """收集一轮图执行的全部事件，超过 CHAT_TURN_TIMEOUT_SECONDS 抛 TimeoutError。"""
    async def collect() -> list[dict]:
        return [event async for event in events]

    return await asyncio.wait_for(collect(), timeout=settings.chat_turn_timeout_seconds)


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
