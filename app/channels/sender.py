"""
经渠道桥把回复发给买家

请求体 {shop_id, buyer_id, text, idempotency_key}，签名方式与入站相同（见 pinduoduo.bridge_signature）。
网络错误、429、5xx 重试（1s、2s、4s），其他 4xx 不重试。没有配置发送地址时只记录不发送（演练模式）。
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import httpx

from app.channels.pinduoduo import bridge_signature

logger = logging.getLogger(__name__)


class SendError(RuntimeError):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class SendResult:
    status: str  # sent / failed / dry_run
    attempts: int
    error: str | None = None


class DryRunSender:
    dry_run = True

    async def send(self, *, shop_id: str, buyer_id: str, text: str, idempotency_key: str) -> None:
        logger.info("渠道演练模式：未配置发送地址，回复只记录不发送 chars=%s", len(text))


class BridgeSender:
    dry_run = False

    def __init__(self, url: str, secret: str, *, timeout: float = 5,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.url = url
        self.secret = secret
        self.timeout = timeout
        self._transport = transport

    async def send(self, *, shop_id: str, buyer_id: str, text: str, idempotency_key: str) -> None:
        body = json.dumps({"shop_id": shop_id, "buyer_id": buyer_id, "text": text,
                           "idempotency_key": idempotency_key}, ensure_ascii=False).encode()
        timestamp = str(int(time.time()))
        headers = {"Content-Type": "application/json", "X-AssistFlow-Timestamp": timestamp,
                   "X-AssistFlow-Signature": bridge_signature(self.secret, timestamp, body)}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                response = await client.post(self.url, content=body, headers=headers)
        except httpx.HTTPError as error:
            raise SendError(f"network: {type(error).__name__}", retryable=True) from error
        if response.status_code == 429 or response.status_code >= 500:
            raise SendError(f"http {response.status_code}", retryable=True)
        if response.status_code >= 400:
            raise SendError(f"http {response.status_code}: {response.text[:120]}", retryable=False)


async def send_with_retry(sender, *, shop_id: str, buyer_id: str, text: str, idempotency_key: str,
                          retries: int = 3, backoff: float = 1.0) -> SendResult:
    attempts = 0
    while True:
        attempts += 1
        try:
            await sender.send(shop_id=shop_id, buyer_id=buyer_id, text=text, idempotency_key=idempotency_key)
        except SendError as error:
            if not error.retryable or attempts > retries:
                logger.warning("渠道消息发送失败 attempts=%s error=%s", attempts, error)
                return SendResult("failed", attempts, str(error))
            await asyncio.sleep(backoff * 2 ** (attempts - 1))
        except Exception as error:  # 不让发送异常打断会话处理
            logger.exception("渠道消息发送异常")
            return SendResult("failed", attempts, type(error).__name__)
        else:
            return SendResult("dry_run" if getattr(sender, "dry_run", False) else "sent", attempts)
