"""
拼多多渠道

消息收发不直接连拼多多，而是经“渠道桥”：桥负责对接拼多多客服消息（客服类应用的授权接口，
或商家已有的客服中间件），把买家消息整理成下面的格式推给本服务，再把本服务的回复发给买家。
这样平台接口的变动、授权和长连接都留在桥里，本服务只认一个稳定的签名接口。

本模块包含：
- 渠道桥签名：HMAC-SHA256(secret, "时间戳.请求体")，时间戳与本机相差超过 5 分钟拒绝
- 入站消息格式（PddInbound）
- 平台话术规则：纯文本，不发外部链接和联系方式（拼多多禁止引导站外交易）
- 开放平台网关签名与订单查询（pdd.order.information.get），用于查询买家发来的订单
"""

import hashlib
import hmac
import json
import logging
import re
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.channels import store
from app.channels.text import plain_text
from app.config import settings
from app.tools.orders import OrderProvider

logger = logging.getLogger(__name__)

CHANNEL = "pinduoduo"
USER_PREFIX = "pdd-"
SIGNATURE_TOLERANCE_SECONDS = 300
ORDER_SN = re.compile(r"\d{6}-\d{10,20}")


# ==================== 渠道桥签名 ====================

def bridge_signature(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_bridge(secret: str, timestamp: str | None, signature: str | None, body: bytes,
                  now: float | None = None) -> bool:
    if not secret or not timestamp or not signature:
        return False
    try:
        sent = int(timestamp)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - sent) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    return hmac.compare_digest(bridge_signature(secret, timestamp, body), signature.lower())


# ==================== 入站消息 ====================

class PddEvent(BaseModel):
    msg_id: str = Field(min_length=1, max_length=128, description="平台消息 ID，用于去重")
    buyer_id: str = Field(min_length=1, max_length=128)
    type: Literal["text", "image", "video", "emoji", "goods", "order", "other"] = "text"
    text: str = Field(default="", max_length=2000)
    order_sn: str | None = Field(default=None, pattern=r"^\d{6}-\d{10,20}$",
                                 description="买家发来的订单卡片（平台带出，可作为订单归属证明）")
    goods_name: str | None = Field(default=None, max_length=255)
    sent_at: int | None = Field(default=None, description="平台发送时间（Unix 秒）")


class PddInbound(BaseModel):
    shop_id: str = Field(min_length=1, max_length=64)
    events: list[PddEvent] = Field(min_length=1, max_length=50)


def event_text(event: PddEvent) -> str | None:
    """入站消息转成交给 AI 的文字；图片、视频等暂不支持的类型返回 None。"""
    text = event.text.strip()
    if event.type == "goods":
        prefix = f"[咨询商品] {event.goods_name}" if event.goods_name else "[咨询商品]"
        return f"{prefix}\n{text}".strip()
    if event.type == "order":
        prefix = f"[订单 {event.order_sn}]" if event.order_sn else "[订单]"
        if event.goods_name:
            prefix += f" {event.goods_name}"
        return f"{prefix}\n{text}".strip()
    if event.type == "text":
        return text or None
    return None


# ==================== 平台话术规则 ====================

_URL = re.compile(r"(?:https?://|www\.)[^\s，。；！？）)]+", re.I)
_PHONE = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8}|400-?\d{3}-?\d{4})(?!\d)")
_CONTACT = re.compile(r"(?:微信|weixin|vx|wx|QQ)[号:： ]*[A-Za-z0-9_-]{5,}", re.I)


def sanitize(text: str) -> str:
    """转成纯文本，去掉外部链接和联系方式（平台规则不允许引导到站外）。"""
    text = plain_text(text)
    text = _URL.sub("", text)
    text = _CONTACT.sub("", text)
    text = _PHONE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


# ==================== 开放平台（订单查询） ====================

class PddApiError(RuntimeError):
    def __init__(self, code, message: str):
        super().__init__(f"{code} {message}")
        self.code = code


def gateway_sign(params: dict[str, str], secret: str) -> str:
    """拼多多开放平台签名：MD5(secret + 按键排序拼接的 key+value + secret)，大写十六进制。"""
    raw = secret + "".join(f"{key}{params[key]}" for key in sorted(params)) + secret
    return hashlib.md5(raw.encode()).hexdigest().upper()


ORDER_STATUS = {1: "待发货", 2: "已发货待签收", 3: "已签收"}
REFUND_STATUS = {2: "售后处理中", 3: "退款中", 4: "退款成功"}


class PddClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(settings.pdd_client_id and settings.pdd_client_secret and settings.pdd_access_token)

    async def call(self, api_type: str, **business) -> dict:
        params = {
            "type": api_type,
            "client_id": settings.pdd_client_id,
            "access_token": settings.pdd_access_token,
            "timestamp": str(int(time.time())),
            "data_type": "JSON",
            **{key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
               for key, value in business.items()},
        }
        params["sign"] = gateway_sign(params, settings.pdd_client_secret)
        async with httpx.AsyncClient(timeout=5, transport=self._transport) as client:
            response = await client.post(settings.pdd_gateway_url, data=params)
            response.raise_for_status()
            data = response.json()
        if "error_response" in data:
            error = data["error_response"]
            raise PddApiError(error.get("error_code"), str(error.get("error_msg") or ""))
        return data

    async def order_info(self, order_sn: str) -> dict | None:
        data = await self.call("pdd.order.information.get", order_sn=order_sn)
        return (data.get("order_info_get_response") or {}).get("order_info")


def order_status_text(info: dict) -> str:
    status = ORDER_STATUS.get(info.get("order_status"), "状态未知")
    refund = REFUND_STATUS.get(info.get("refund_status"))
    return f"{status}，{refund}" if refund else status


class PddOrderProvider(OrderProvider):
    """拼多多顾客的订单：只认买家在会话里发过订单卡片的订单（平台带出的归属），再到开放平台查状态。"""

    def __init__(self, client: PddClient | None = None):
        self.client = client or PddClient()

    def handles_user(self, user_id: str) -> bool:
        return (user_id or "").startswith(USER_PREFIX)

    def handles_order(self, order_id: str) -> bool:
        return bool(ORDER_SN.fullmatch(order_id or ""))

    async def get(self, order_id: str) -> dict | None:
        owned = await store.order_owner(CHANNEL, order_id)
        if owned is None:
            return None
        order = {"order_id": order_id, "user_id": owned["user_id"],
                 "product_name": owned.get("goods_name") or "", "status": "暂时查不到状态"}
        if not self.client.configured:
            return order
        try:
            info = await self.client.order_info(order_id)
        except Exception as error:
            logger.warning("拼多多订单查询失败 error_type=%s", type(error).__name__)
            return order
        if info:
            goods = info.get("item_list") or info.get("goods_list") or []
            if goods and goods[0].get("goods_name"):
                order["product_name"] = goods[0]["goods_name"]
            order["status"] = order_status_text(info)
            if info.get("tracking_number"):
                order["tracking_number"] = info["tracking_number"]
        return order

    async def list_for_user(self, user_id: str) -> list[dict]:
        return [{"order_id": row["order_id"], "user_id": user_id, "product_name": row.get("goods_name") or "",
                 "status": ""} for row in await store.orders_for_user(CHANNEL, user_id)]
