import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.chat import graph_event_to_sse, restore_messages, make_sse
from app.db import repository
from app.core.conversation_lock import conversation_lock
from app.graph.runtime import Runtime
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
    runtime: Runtime, user_id: str, conversation_id: int,
) -> None:
    snapshot = await runtime.graph.aget_state(_thread_config(user_id, conversation_id))
    await repository.persist_graph_messages(
        conversation_id, user_id, snapshot.values.get("messages", []),
    )


async def stream_graph_chat(
    request: ChatRequest, conversation_id: int, runtime: Runtime,
) -> AsyncIterator[str]:
    try:
        yield make_sse({"event": "conversation", "conversation_id": conversation_id})
        async with conversation_lock(request.user_id, conversation_id):
            config = _thread_config(request.user_id, conversation_id)
            snapshot = await runtime.graph.aget_state(config)
            if not snapshot.values:
                history = restore_messages(await repository.list_messages(conversation_id))
                if history:
                    await runtime.graph.aupdate_state(config, {"messages": history}, as_node="finish")
            events = [event async for event in runtime.stream_turn(
                request.message, request.user_id, str(conversation_id),
            )]
            # 即使模型失败，也保存已提交的图步骤；游标保证重试不重复保存。
            await _persist_graph_messages(runtime, request.user_id, conversation_id)
        for event in events:
            if event.get("event") != "end":
                yield graph_event_to_sse(event, conversation_id)
    except Exception:
        logger.exception("图聊天失败 conversation_id=%s", conversation_id)
        yield 'event: error\ndata: {"message":"图执行或消息保存失败，请重试"}\n\n'
    finally:
        yield "data: [DONE]\n\n"


@router.post("/graph-chat")
async def graph_chat(
    request: ChatRequest,
    http_request: Request,
) -> StreamingResponse:
    runtime: Runtime | None = getattr(http_request.app.state, "graph_runtime", None)
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
