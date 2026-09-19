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
from app.tools.order_tools import query_order
from app.core.llm import get_chat_model
from app.core.prompts import CHAT_SYSTEM_PROMPT
from app.schemas.chat import ChatRequest
from app.tools.ticket_tools import create_ticket
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

MAX_TOOL_ROUNDS = 3
TOOL_BY_NAME=[query_order, create_ticket]
def make_sse(data: dict) -> str:
    """把字典编码成一个以空行结尾的 SSE 数据帧。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"data: {payload}\n\n"
def restore_messages(records: list) -> list:
    """把数据库消息恢复为 LangChain 消息。"""
    messages = []

    for record in records:
        if record.role == "user":
            messages.append(HumanMessage(content=record.content or ""))
        elif record.role == "assistant":
            messages.append(
                AIMessage(
                    content=record.content or "",
                    tool_calls=record.tool_calls or [],
                )
            )
        elif record.role == "tool":
            messages.append(
                ToolMessage(
                    content=record.content or "",
                    tool_call_id=record.tool_call_id or "",
                )
            )

    return messages
async def stream_chat(
    request: ChatRequest,
    conversation_id: int,
) -> AsyncIterator[str]:
    """调用模型并依次产出回答片段、完成事件和流结束标记。

    成功时保存完整的一轮消息；模型中途失败时只返回安全错误，
    不把半截回答写入会话历史。
    """

    model = get_chat_model(streaming=False).bind_tools(TOOL_BY_NAME)
    records = await repository.list_messages(conversation_id)
    history = restore_messages(records)

    messages = [
        SystemMessage(content=CHAT_SYSTEM_PROMPT),
        *history,
        HumanMessage(content=request.message),
    ]
    await repository.append_message(
        conversation_id,
        "user",
        request.message,
    )

    working_messages = list(messages)

    answer = "工具调用次数过多，请稍后重试"

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            ai_message = await model.ainvoke(working_messages)
            working_messages.append(ai_message)
            await repository.append_message(
                conversation_id,
                "assistant",
                str(ai_message.content),
                tool_calls=ai_message.tool_calls or None,
            )
            if not ai_message.tool_calls:
                answer = str(ai_message.content)
                break
            pending_interrupt = None
            for tool_call in ai_message.tool_calls:
                try:
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

                    elif tool_call["name"] == create_ticket.name:
                        if pending_interrupt is None:
                            preview = await create_ticket.ainvoke(
                                tool_call["args"]
                            )
                            pending_interrupt = {
                                "event": "interrupt",
                                "kind": "confirm_ticket",
                                "conversation_id": conversation_id,
                                "preview": {
                                    "ticket_type": preview["ticket_type"],
                                    "description": preview["description"],
                                },
                            }
                            # 这一条等用户确认后，由 resume 补上工具结果。
                            continue

                        # 当前界面一次只确认一张工单。
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
            if pending_interrupt is not None:
                yield make_sse(pending_interrupt)
                return
        yield make_sse({"delta": answer})



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
        # [DONE] 只表示传输结束；业务是否成功由 done 或 error 事件区分。
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """接收聊天请求并返回 text/event-stream 流式响应。

    首次请求生成临时会话编号，续聊请求继续使用前端传入的编号。
    """
    if request.conversation_id is None:
        conversation_id = await repository.create_conversation(
            request.user_id
        )
    else:
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

    return StreamingResponse(
        stream_chat(request, conversation_id),
        media_type="text/event-stream",
    )
