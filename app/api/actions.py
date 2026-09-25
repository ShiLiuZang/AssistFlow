import logging
import time

from collections.abc import AsyncIterator
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.schemas.actions import ResumeTicketRequest, SelectOrderRequest
from app.api.chat import make_sse, graph_event_to_sse
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
            started = time.monotonic()
            result = await repository.decide_ticket(
                request.conversation_id,
                request.user_id,
                call_id,
                request.confirmed,
                graph=is_graph,
            )
            duration_ms = int((time.monotonic() - started) * 1000)

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
            completed_graph_turn = False
            if is_graph and not interrupts:
                latest = await runtime.graph.aget_state(
                    _thread_config(request.user_id, request.conversation_id)
                )
                completed_graph_turn = not latest.next

        if completed_graph_turn:
            schedule_persisted_summary(
                request.user_id,
                request.conversation_id,
                summarize_dialog,
            )
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
    try:
        async with conversation_lock(
            request.user_id,
            request.conversation_id,
        ):
            resume = request.model_dump(
                include={"kind", "request_id", "order_id", "cancelled"},
                exclude_none=True,
            )

            events = [
                event
                async for event in runtime.stream_turn(
                    "",
                    request.user_id,
                    str(request.conversation_id),
                    resume=resume,
                )
            ]

            await _persist_graph_messages(
                runtime,
                request.user_id,
                request.conversation_id,
            )
        completed = any(e.get("event") == "done" for e in events)
        interrupted_or_failed = any(
            e.get("event") in {"interrupt", "error"} for e in events
        )
        if completed and not interrupted_or_failed:
            schedule_persisted_summary(
                request.user_id,
                request.conversation_id,
                summarize_dialog,
            )
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
    if await repository.get_conversation(conversation_id, user_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    async with conversation_lock(user_id, conversation_id):
        runtime = getattr(http_request.app.state, "graph_runtime", None)
        if runtime is not None:
            snapshot = await runtime.graph.aget_state(_thread_config(user_id, conversation_id))
            pending = _interrupt(snapshot)
            if pending and pending.get("kind") == "select_order":
                return {
                    **pending,
                    "conversation_id": conversation_id,
                }
            if pending:
                saved = await repository.get_ticket_decision(conversation_id, pending["tool_call_id"])
                return {**pending, "conversation_id": conversation_id,
                        "confirmed": saved["confirmed"] if saved else None}
        call = await repository.get_pending_ticket_call(conversation_id)
        if call is None:
            return None
        saved = await repository.get_ticket_decision(conversation_id, call["id"])
        return {"kind": "confirm_ticket", "conversation_id": conversation_id,
                "tool_call_id": call["id"], "preview": call["args"],
                "confirmed": saved["confirmed"] if saved else None}





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

@router.post("/select-order")
async def select_order(
    request: SelectOrderRequest,
    http_request: Request,
) -> StreamingResponse:
    conversation = await repository.get_conversation(
        request.conversation_id,
        request.user_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    runtime = getattr(
        http_request.app.state,
        "graph_runtime",
        None,
    )
    if runtime is None:
        raise HTTPException(status_code=503, detail="图服务尚未就绪")

    return StreamingResponse(
        stream_order_selection(request, runtime),
        media_type="text/event-stream",
    )
