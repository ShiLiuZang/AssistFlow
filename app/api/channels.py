"""
外部渠道接口

- POST /api/channels/pinduoduo/events：渠道桥推送买家消息（HMAC 签名，不用员工或顾客令牌）
- GET /api/channels/status：管理员查看渠道收发情况
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.channels import service, store
from app.channels.pinduoduo import CHANNEL, PddInbound, verify_bridge
from app.config import settings
from app.core.auth import require_admin

router = APIRouter(prefix="/api/channels", tags=["channels"])

MAX_BODY_BYTES = 256 * 1024


@router.post("/pinduoduo/events", status_code=202)
async def pinduoduo_events(request: Request) -> dict:
    """
    接收渠道桥推送的买家消息。

    先校验签名（X-AssistFlow-Timestamp / X-AssistFlow-Signature），登记去重后立即返回；
    回答经渠道桥的发送接口异步发出。平台重试同一消息 ID 时返回在 duplicates 里，不会重复回答。
    """
    dispatcher = service.dispatcher
    if not settings.pdd_enabled or dispatcher is None:
        raise HTTPException(status_code=404, detail="拼多多渠道未开启")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="请求体过大")
    if not verify_bridge(settings.pdd_bridge_secret.strip(), request.headers.get("X-AssistFlow-Timestamp"),
                         request.headers.get("X-AssistFlow-Signature"), body):
        raise HTTPException(status_code=401, detail="签名无效或已过期")
    try:
        payload = PddInbound.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_url=False, include_input=False)) from None
    return await dispatcher.receive(payload)


@router.get("/status", dependencies=[Depends(require_admin)])
async def channel_status() -> dict:
    data = {
        "channel": CHANNEL,
        "enabled": settings.pdd_enabled,
        "running": service.dispatcher is not None,
        "send_mode": "bridge" if settings.pdd_bridge_send_url.strip() else "dry_run",
        "order_api": bool(settings.pdd_client_id and settings.pdd_client_secret and settings.pdd_access_token),
    }
    if settings.pdd_enabled:
        data["stats"] = await store.stats(CHANNEL)
    return data
