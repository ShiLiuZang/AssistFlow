import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.chat import make_sse
from app.db import repository
from app.schemas.actions import ResumeTicketRequest


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/actions", tags=["actions"])


async def stream_ticket_decision(
    request: ResumeTicketRequest,
    tool_call: dict,
) -> AsyncIterator[str]:
    try:
        args = dict(tool_call.get("args") or {})

        if request.confirmed:
            ticket_no = await repository.create_ticket(
                request.conversation_id,
                str(args.get("ticket_type") or "咨询"),
                str(args.get("description") or ""),
            )
            result = {"confirmed": True, "ticket_no": ticket_no}
            answer = f"工单已创建，工单号：{ticket_no}"
        else:
            result = {"confirmed": False, "message": "用户取消建单"}
            answer = "已取消，本次没有创建工单。"

        # 先闭合 assistant 的工具调用，再记录用户确认，避免破坏模型消息协议。
        await repository.append_message(
            request.conversation_id,
            "tool",
            json.dumps(result, ensure_ascii=False),
            tool_call_id=str(tool_call["id"]),
        )
        await repository.append_message(
            request.conversation_id,
            "user",
            "确认提交工单" if request.confirmed else "取消建单",
        )
        await repository.append_message(
            request.conversation_id,
            "assistant",
            answer,
        )

        yield make_sse({"delta": answer})
        yield make_sse(
            {
                "event": "done",
                "conversation_id": request.conversation_id,
            }
        )
    except Exception:
        logger.exception("处理工单确认失败 conversation_id=%s", request.conversation_id)
        yield "event: error\ndata: {\"message\":\"工单处理失败\"}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@router.post("/resume")
async def resume_ticket(request: ResumeTicketRequest) -> StreamingResponse:
    conversation = await repository.get_conversation(
        request.conversation_id,
        request.user_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    tool_call = await repository.get_pending_ticket_call(request.conversation_id)
    if tool_call is None:
        raise HTTPException(status_code=409, detail="没有待确认的工单")

    return StreamingResponse(
        stream_ticket_decision(request, tool_call),
        media_type="text/event-stream",
    )
