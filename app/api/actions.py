import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.chat import make_sse, graph_event_to_sse
from app.api.graph_chat import _thread_config, _persist_graph_messages
from app.core.conversation_lock import conversation_lock
from app.db import repository
from app.graph.runtime import Runtime
from app.schemas.actions import ResumeTicketRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/actions", tags=["actions"])


def _interrupt(snapshot):
    return next((item.value for task in snapshot.tasks for item in task.interrupts), None)


def _call_in_current_turn(snapshot, call_id: str) -> bool:
    for message in reversed(snapshot.values.get("messages", [])):
        if message.type == "human":
            return False
        if any(call["id"] == call_id for call in getattr(message, "tool_calls", [])):
            return True
    return False


async def stream_ticket_decision(
    request: ResumeTicketRequest, tool_call: dict, runtime: Runtime | None = None,
) -> AsyncIterator[str]:
    try:
        async with conversation_lock(request.user_id, request.conversation_id):
            call_id = str(tool_call["id"])
            graph_result = None
            snapshot = None
            pending = None
            if runtime is not None:
                snapshot = await runtime.graph.aget_state(
                    _thread_config(request.user_id, request.conversation_id),
                )
                pending = _interrupt(snapshot)
            saved = await repository.get_ticket_decision(request.conversation_id, call_id)
            if pending and pending.get("tool_call_id") != call_id and saved is None:
                raise ValueError("确认调用与当前中断不匹配")
            is_graph = bool(snapshot and snapshot.values)
            if is_graph and saved is None and not pending:
                raise ValueError("没有待恢复的工单中断")
            result = await repository.decide_ticket(
                request.conversation_id, request.user_id, call_id,
                request.confirmed, graph=is_graph,
            )
            if pending and pending.get("tool_call_id") == call_id:
                graph_result = await runtime.run_turn(
                    "", request.user_id, str(request.conversation_id),
                    resume={"tool_call_id": call_id, "tool_result": result},
                )
            elif is_graph and snapshot.next and not pending and _call_in_current_turn(snapshot, call_id):
                # 确认已入库但后续节点失败：从检查点重试，不再创建工单。
                graph_result = await runtime.graph.ainvoke(
                    None, _thread_config(request.user_id, request.conversation_id),
                )
            elif is_graph:
                # 旧确认卡重放不能确认下一张卡；返回当前等待状态。
                graph_result = dict(snapshot.values)
                if pending:
                    graph_result["__interrupt__"] = [
                        item for task in snapshot.tasks for item in task.interrupts
                    ]
            if is_graph:
                await _persist_graph_messages(runtime, request.user_id, request.conversation_id)
            interrupts = graph_result.get("__interrupt__") if graph_result else None
            frames = []
            if interrupts:
                frames.append(graph_event_to_sse(
                    {"event": "interrupt", "preview": interrupts[0].value},
                    request.conversation_id,
                ))
            else:
                frames.append(make_sse({"delta": repository.ticket_answer(result)}))
                frames.append(make_sse({"event": "done", "conversation_id": request.conversation_id}))
        for frame in frames:
            yield frame
    except Exception:
        logger.exception("处理工单确认失败 conversation_id=%s", request.conversation_id)
        yield 'event: error\ndata: {"message":"工单处理或图恢复失败，请重试同一确认请求"}\n\n'
    finally:
        yield "data: [DONE]\n\n"


@router.post("/resume")
async def resume_ticket(request: ResumeTicketRequest, http_request: Request) -> StreamingResponse:
    conversation = await repository.get_conversation(request.conversation_id, request.user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    runtime = getattr(http_request.app.state, "graph_runtime", None)
    call_id = request.tool_call_id
    if runtime is not None:
        snapshot = await runtime.graph.aget_state(_thread_config(request.user_id, request.conversation_id))
        if snapshot.values and call_id is None:
            raise HTTPException(status_code=409, detail="图确认必须携带工具调用 ID")
    if call_id is None:
        pending = await repository.get_pending_ticket_call(request.conversation_id)
        if pending is None:
            raise HTTPException(status_code=409, detail="没有待确认的工单")
        call_id = str(pending["id"])
    records = await repository.list_messages(request.conversation_id)
    tool_call = next((call for record in reversed(records) for call in record.tool_calls or []
                      if call.get("id") == call_id and call.get("name") == "create_ticket"), None)
    if tool_call is None:
        raise HTTPException(status_code=409, detail="没有对应的工单调用")
    return StreamingResponse(stream_ticket_decision(request, tool_call, runtime),
                             media_type="text/event-stream")
