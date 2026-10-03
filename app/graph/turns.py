"""
一轮对话的执行：网页聊天接口和渠道调度共用

每个入口函数都在会话锁内完成「读图状态 → 跑图 → 消息落库 → 调度摘要」，
返回事件字典列表，不涉及传输格式：网页端编码成 SSE（app.api.sse），渠道端转成纯文本（app.channels.dispatcher）。
入口函数不抛业务异常，失败统一返回一条 {"event": "error", "message": ...}。

事件：
- {"event": "handoff", ...}            人工接待状态
- {"delta": "..."}                     回答文本
- {"event": "tool" / "citations", ...} 工具调用、引用（citations 字段改名为 items）
- {"event": "interrupt", "kind": ..., "conversation_id": ...}  待用户确认（中断预览已展开）
- {"event": "done", "conversation_id": ..., ["handoff": True]}
- {"event": "error", "message": "..."}
"""

import asyncio
import json
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.config import settings
from app.core import handoff
from app.core.conversation_lock import conversation_lock
from app.core.observability import span
from app.core.summarizer import schedule_persisted_summary, summarize_dialog
from app.db import conversation_repo, ticket_repo, trace_repo
from app.graph.runtime import Runtime
from app.schemas.actions import ResumeTicketRequest, SelectOrderRequest
from app.schemas.chat import ChatRequest
from app.tools.audit import build_ticket_decision_audit, emit_tool_audit
from app.tools.engine import classify_tool_result

logger = logging.getLogger(__name__)

TIMEOUT_MESSAGE = "当前咨询较多，请稍后重试或转人工"
GRAPH_ERROR_MESSAGE = "图执行失败，请重试"


def error_event(message: str) -> dict:
    return {"event": "error", "message": message}


# ==================== 图状态 ====================

def thread_config(user_id: str, conversation_id: int) -> dict:
    """LangGraph 线程配置：thread_id 为「用户ID:会话ID」，每个会话一份图状态。"""
    return {"configurable": {"thread_id": f"{user_id}:{conversation_id}"}}


def snapshot_interrupt(snapshot):
    """图快照里的第一个中断（待确认操作），没有时返回 None。"""
    return next((item.value for task in snapshot.tasks for item in task.interrupts), None)


async def pending_interrupt(runtime: Runtime, user_id: str, conversation_id: int):
    """在会话锁内读取当前待确认操作。"""
    async with conversation_lock(user_id, conversation_id):
        return snapshot_interrupt(await runtime.graph.aget_state(thread_config(user_id, conversation_id)))


async def find_ticket_call(conversation_id: int, call_id: str) -> dict | None:
    """从消息历史里找到对应的 create_ticket 工具调用。"""
    records = await conversation_repo.list_messages(conversation_id)
    return next((call for record in reversed(records) for call in record.tool_calls or []
                 if call.get("id") == call_id and call.get("name") == "create_ticket"), None)


def call_in_current_turn(snapshot, call_id: str) -> bool:
    """工具调用是否属于当前轮次：从最新消息往前找，遇到用户消息（轮次边界）就停。"""
    for message in reversed(snapshot.values.get("messages", [])):
        if message.type == "human":
            return False
        if any(call["id"] == call_id for call in getattr(message, "tool_calls", [])):
            return True
    return False


async def persist_graph_messages(runtime: Runtime, user_id: str, conversation_id: int) -> None:
    """把图状态里的消息同步到数据库（图是真实来源）。"""
    snapshot = await runtime.graph.aget_state(thread_config(user_id, conversation_id))
    await conversation_repo.persist_graph_messages(conversation_id, user_id, snapshot.values.get("messages", []))


async def collect_turn(events) -> list[dict]:
    """收集一轮图执行的全部事件，超过 CHAT_TURN_TIMEOUT_SECONDS 抛 TimeoutError。"""
    async def collect() -> list[dict]:
        return [event async for event in events]

    return await asyncio.wait_for(collect(), timeout=settings.chat_turn_timeout_seconds)


# ==================== 历史恢复与校验 ====================

def restored_tool_status(content: str) -> str:
    """从工具消息内容恢复执行状态：能解析且分类为 success 才算成功。"""
    try:
        result = json.loads(content)
    except (TypeError, ValueError):
        return "error"
    return "success" if classify_tool_result(result) == "success" else "error"


def restore_messages(records: list) -> list:
    """数据库消息记录恢复为 LangChain 消息（user/assistant/tool）。"""
    messages = []
    for record in records:
        if record.role == "user":
            messages.append(HumanMessage(content=record.content or ""))
        elif record.role == "assistant":
            messages.append(AIMessage(content=record.content or "", tool_calls=record.tool_calls or [],
                                      id=record.turn_message_id))
        elif record.role == "tool":
            content = record.content or ""
            messages.append(ToolMessage(content=content, tool_call_id=record.tool_call_id or "",
                                        status=restored_tool_status(content)))
    return messages


def count_covered_messages(records, graph_messages, summary_upto: int) -> int:
    """
    计算已被摘要覆盖的消息数量，并校验图消息与数据库消息一致

    数据库历史不能比图历史长；逐条比对类型、内容、工具调用；摘要游标必须指向一条模型消息。
    不一致时抛 ValueError。
    """
    roles = {"user": "human", "assistant": "ai", "tool": "tool"}
    rows = [row for row in records if row.role in roles]
    if len(rows) > len(graph_messages):
        raise ValueError("数据库历史比图历史长")
    for row, message in zip(rows, graph_messages):
        if (
            message.type != roles[row.role]
            or str(message.content) != (row.content or "")
            or (getattr(message, "tool_calls", None) or []) != (row.tool_calls or [])
            or getattr(message, "tool_call_id", None) != row.tool_call_id
        ):
            raise ValueError(f"图消息与数据库消息不一致：{row.id}")
    if summary_upto and not any(row.id == summary_upto for row in rows):
        raise ValueError("摘要游标未指向一条模型消息")
    return sum(row.id <= summary_upto for row in rows)


# ==================== 事件整理 ====================

def normalize_event(event: dict, conversation_id: int) -> dict | None:
    """图运行时事件转成对外事件；end 事件返回 None。"""
    if event.get("event") == "end":
        return None
    if event.get("event") == "error":
        return error_event(GRAPH_ERROR_MESSAGE)
    payload = dict(event)
    if payload.get("event") == "citations":
        payload["items"] = payload.pop("citations", [])
    if payload.get("event") in {"done", "interrupt"}:
        payload["conversation_id"] = conversation_id
    if payload.get("event") == "interrupt":
        payload.update(payload.pop("preview"))
    return payload


def _normalize_all(events: list[dict], conversation_id: int) -> list[dict]:
    return [item for item in (normalize_event(event, conversation_id) for event in events) if item is not None]


def _completed(events: list[dict]) -> bool:
    """本轮正常结束（有 done，没有中断和错误）。"""
    return (any(e.get("event") == "done" for e in events)
            and not any(e.get("event") in {"interrupt", "error"} for e in events))


# ==================== 入口 ====================

async def chat_turn(request: ChatRequest, conversation_id: int, runtime: Runtime) -> list[dict]:
    """
    顾客发来一条新消息

    人工接待中直接交给坐席；否则从图状态（为空时从数据库）恢复历史，跑一轮图，消息落库，
    正常结束时调度摘要。
    """
    try:
        async with conversation_lock(request.user_id, conversation_id):
            routed = await handoff.customer_message(conversation_id, request.user_id, request.message)
            if routed is not None:
                return [{"event": "handoff", "conversation_id": conversation_id, **routed},
                        {"event": "done", "conversation_id": conversation_id, "message_id": None,
                         "handoff": True}]

            config = thread_config(request.user_id, conversation_id)
            snapshot = await runtime.graph.aget_state(config)
            conversation = await conversation_repo.get_conversation(conversation_id, request.user_id)
            if conversation is None:
                raise ValueError("会话不存在")
            records = await conversation_repo.list_messages(conversation_id)
            graph_messages = (restore_messages(records) if not snapshot.values
                              else snapshot.values.get("messages", []))
            covered_count = count_covered_messages(records, graph_messages, conversation.summary_upto or 0)
            if not snapshot.values and graph_messages:
                await runtime.graph.aupdate_state(config, {"messages": graph_messages}, as_node="finish")

            events = await collect_turn(runtime.stream_turn(
                request.message, request.user_id, str(conversation_id),
                summary_text=conversation.summary_text or "",
                summary_upto=conversation.summary_upto or 0,
                covered_count=covered_count,
            ))
            await persist_graph_messages(runtime, request.user_id, conversation_id)

        if _completed(events):
            schedule_persisted_summary(request.user_id, conversation_id, summarize_dialog)

        result = []
        # 本轮转入了人工排队（human / complaint 节点），先告诉调用方接待状态
        try:
            state = await handoff.open_status(conversation_id)
        except Exception:
            logger.warning("读取人工接待状态失败 conversation_id=%s", conversation_id, exc_info=True)
            state = None
        if state is not None:
            result.append({"event": "handoff", "conversation_id": conversation_id, "handoff": state})
        return result + _normalize_all(events, conversation_id)
    except TimeoutError:
        logger.warning("图聊天超时 conversation_id=%s", conversation_id)
        return [error_event(TIMEOUT_MESSAGE)]
    except Exception:
        logger.exception("图聊天失败 conversation_id=%s", conversation_id)
        return [error_event("图执行或消息保存失败，请重试")]


async def ticket_decision_turn(
    request: ResumeTicketRequest, tool_call: dict, runtime: Runtime | None = None,
) -> list[dict]:
    """
    顾客确认或取消工单

    保存决策（确认时创建工单）并写审计；图里有对应中断就恢复执行，
    图停在当前轮次中间就继续执行，否则沿用当前图状态。已保存的决策允许重复提交（幂等）。
    """
    try:
        async with (
            span("ticket_action", trace_repo.insert_trace_span),
            conversation_lock(request.user_id, request.conversation_id),
        ):
            call_id = str(tool_call["id"])
            config = thread_config(request.user_id, request.conversation_id)
            graph_result = snapshot = pending = None
            if runtime is not None:
                snapshot = await runtime.graph.aget_state(config)
                pending = snapshot_interrupt(snapshot)

            saved = await ticket_repo.get_ticket_decision(request.conversation_id, call_id)
            if pending and pending.get("tool_call_id") != call_id and saved is None:
                raise ValueError("确认调用与当前中断不匹配")
            is_graph = bool(snapshot and snapshot.values)
            if is_graph and saved is None and not pending:
                raise ValueError("没有待恢复的工单中断")

            async with span("ticket_decision", trace_repo.insert_trace_span):
                started = time.monotonic()
                result = await ticket_repo.decide_ticket(request.conversation_id, request.user_id, call_id,
                                                        request.confirmed, graph=is_graph)
                duration_ms = int((time.monotonic() - started) * 1000)

            try:
                audit_record = build_ticket_decision_audit(tool_call, request.conversation_id, result, duration_ms)
            except Exception as error:
                logger.warning("工单审计记录构造失败：error_type=%s", type(error).__name__)
            else:
                await emit_tool_audit(trace_repo.insert_tool_audit, audit_record)

            if pending and pending.get("tool_call_id") == call_id:
                graph_result = await runtime.run_turn(
                    "", request.user_id, str(request.conversation_id),
                    resume={"tool_call_id": call_id, "tool_result": result},
                )
            elif is_graph and snapshot.next and not pending and call_in_current_turn(snapshot, call_id):
                async with span("graph_turn", trace_repo.insert_trace_span):
                    graph_result = await runtime.graph.ainvoke(None, config)
            elif is_graph:
                graph_result = dict(snapshot.values)
                if pending:
                    graph_result["__interrupt__"] = [item for task in snapshot.tasks for item in task.interrupts]

            if is_graph:
                await persist_graph_messages(runtime, request.user_id, request.conversation_id)

            interrupts = graph_result.get("__interrupt__") if graph_result else None
            if interrupts:
                events = [normalize_event({"event": "interrupt", "preview": interrupts[0].value},
                                          request.conversation_id)]
            else:
                events = [{"delta": ticket_repo.ticket_answer(result)},
                          {"event": "done", "conversation_id": request.conversation_id}]

            completed_graph_turn = False
            if is_graph and not interrupts:
                completed_graph_turn = not (await runtime.graph.aget_state(config)).next

        if completed_graph_turn:
            schedule_persisted_summary(request.user_id, request.conversation_id, summarize_dialog)
        return events
    except Exception:
        logger.exception("处理工单确认失败 conversation_id=%s", request.conversation_id)
        return [error_event("工单处理或图恢复失败，请重试同一确认请求")]


async def order_selection_turn(request: SelectOrderRequest, runtime: Runtime) -> list[dict]:
    """顾客在多笔订单里选了一笔（或取消），恢复图执行。"""
    try:
        async with conversation_lock(request.user_id, request.conversation_id):
            resume = request.model_dump(include={"kind", "request_id", "order_id", "cancelled"}, exclude_none=True)
            events = await collect_turn(runtime.stream_turn(
                "", request.user_id, str(request.conversation_id), resume=resume,
            ))
            await persist_graph_messages(runtime, request.user_id, request.conversation_id)

        if _completed(events):
            schedule_persisted_summary(request.user_id, request.conversation_id, summarize_dialog)
        return _normalize_all(events, request.conversation_id)
    except TimeoutError:
        logger.warning("订单选择超时 conversation_id=%s", request.conversation_id)
        return [error_event(TIMEOUT_MESSAGE)]
    except Exception:
        logger.exception("订单选择或消息保存失败 conversation_id=%s", request.conversation_id)
        return [error_event("订单选择或消息保存失败，请检查当前待处理状态")]
