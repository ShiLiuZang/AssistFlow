import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, ToolMessage

from app.api.chat import graph_event_to_sse
from app.db import repository
from app.schemas.chat import ChatRequest


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["graph-chat"])


def _thread_config(user_id: str, conversation_id: int) -> dict:
    return {
        "configurable": {
            "thread_id": f"{user_id}:{conversation_id}",
        },
    }


async def _persist_graph_messages(
    runtime,
    user_id: str,
    conversation_id: int,
    start: int,
) -> None:
    snapshot = await runtime.graph.aget_state(
        _thread_config(user_id, conversation_id),
    )
    messages = snapshot.values.get("messages", [])[start:]

    for message in messages:
        if isinstance(message, AIMessage):
            await repository.append_message(
                conversation_id,
                "assistant",
                str(message.content),
                tool_calls=message.tool_calls or None,
            )
        elif isinstance(message, ToolMessage):
            await repository.append_message(
                conversation_id,
                "tool",
                str(message.content),
                tool_call_id=message.tool_call_id,
            )


async def stream_graph_chat(
    request: ChatRequest,
    conversation_id: int,
    runtime,
) -> AsyncIterator[str]:
    config = _thread_config(request.user_id, conversation_id)
    before = await runtime.graph.aget_state(config)
    start = len(before.values.get("messages", []))

    await repository.append_message(
        conversation_id,
        "user",
        request.message,
    )

    events = [
        event
        async for event in runtime.stream_turn(
            request.message,
            request.user_id,
            str(conversation_id),
        )
    ]
    has_error = any(event.get("event") == "error" for event in events)
    can_persist = any(
        event.get("event") in {"done", "interrupt"}
        for event in events
    )

    if can_persist and not has_error:
        await _persist_graph_messages(
            runtime,
            request.user_id,
            conversation_id,
            start,
        )

    for event in events:
        yield graph_event_to_sse(event, conversation_id)


@router.post("/graph-chat")
async def graph_chat(
    request: ChatRequest,
    http_request: Request,
) -> StreamingResponse:
    runtime = getattr(http_request.app.state, "graph_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="图服务未启动")

    if request.conversation_id is None:
        conversation_id = await repository.create_conversation(request.user_id)
    else:
        conversation = await repository.get_conversation(
            request.conversation_id,
            request.user_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        conversation_id = conversation.id
        if await repository.get_pending_ticket_call(conversation_id) is not None:
            raise HTTPException(status_code=409, detail="请先确认或取消待处理工单")

    return StreamingResponse(
        stream_graph_chat(request, conversation_id, runtime),
        media_type="text/event-stream",
    )
