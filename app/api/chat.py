import json
import logging
from collections.abc import AsyncIterator
from itertools import count

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

from app.core.llm import get_chat_model
from app.core.prompts import CHAT_SYSTEM_PROMPT
from app.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])
conversation_ids = count(1)
# Ch01 只用进程内字典演示多轮对话；服务重启后历史会丢失。
conversation_histories: dict[int, list] = {}


def make_sse(data: dict) -> str:
    """把字典编码成一个以空行结尾的 SSE 数据帧。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"data: {payload}\n\n"


async def stream_chat(
    request: ChatRequest,
    conversation_id: int,
) -> AsyncIterator[str]:
    """调用模型并依次产出回答片段、完成事件和流结束标记。

    成功时保存完整的一轮消息；模型中途失败时只返回安全错误，
    不把半截回答写入会话历史。
    """
    model = get_chat_model(streaming=True)

    if conversation_id not in conversation_histories:
        conversation_histories[conversation_id] = []

    history = conversation_histories[conversation_id]

    messages = [
        SystemMessage(content=CHAT_SYSTEM_PROMPT),
        *history,
        HumanMessage(content=request.message),
    ]
    answer_parts: list[str] = []
    try:
        async for chunk in model.astream(messages):
            if isinstance(chunk.content, str) and chunk.content:
                answer_parts.append(chunk.content)
                yield make_sse({"delta": chunk.content})

        conversation_histories[conversation_id].extend(
            [
                HumanMessage(content=request.message),
                AIMessage(content="".join(answer_parts)),
            ]
        )

        yield make_sse(
            {
                "event": "done",
                "conversation_id": conversation_id,
            }
        )
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
    conversation_id = request.conversation_id or next(conversation_ids)

    return StreamingResponse(
        stream_chat(request, conversation_id),
        media_type="text/event-stream",
    )
