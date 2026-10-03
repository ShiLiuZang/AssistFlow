"""渠道桥发送：签名、重试、演练模式。"""
import json

import httpx

from app.channels import sender as sender_module
from app.channels.pinduoduo import verify_bridge
from app.channels.sender import BridgeSender, DryRunSender, send_with_retry

SECRET = "s" * 32


def bridge(responses, seen):
    def handler(request):
        seen.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return httpx.Response(response)
    return BridgeSender("https://bridge.example/send", SECRET, transport=httpx.MockTransport(handler))


async def no_sleep(_):
    return None


class TestBridgeSender:
    async def test_signed_body(self):
        seen = []
        result = await send_with_retry(bridge([200], seen), shop_id="s1", buyer_id="b1", text="你好",
                                       idempotency_key="k1")
        assert (result.status, result.attempts) == ("sent", 1)
        request = seen[0]
        assert json.loads(request.content) == {"shop_id": "s1", "buyer_id": "b1", "text": "你好",
                                               "idempotency_key": "k1"}
        assert verify_bridge(SECRET, request.headers["X-AssistFlow-Timestamp"],
                             request.headers["X-AssistFlow-Signature"], request.content)

    async def test_retries_transient_errors(self, monkeypatch):
        monkeypatch.setattr(sender_module.asyncio, "sleep", no_sleep)
        seen = []
        responses = [httpx.ConnectError("down"), 503, 429, 200]
        result = await send_with_retry(bridge(responses, seen), shop_id="s", buyer_id="b", text="t",
                                       idempotency_key="k")
        assert (result.status, result.attempts) == ("sent", 4)

    async def test_gives_up_after_retries(self, monkeypatch):
        monkeypatch.setattr(sender_module.asyncio, "sleep", no_sleep)
        seen = []
        result = await send_with_retry(bridge([500] * 4, seen), shop_id="s", buyer_id="b", text="t",
                                       idempotency_key="k", retries=3)
        assert (result.status, result.attempts, result.error) == ("failed", 4, "http 500")

    async def test_client_error_not_retried(self):
        seen = []
        result = await send_with_retry(bridge([400], seen), shop_id="s", buyer_id="b", text="t",
                                       idempotency_key="k")
        assert (result.status, result.attempts) == ("failed", 1) and len(seen) == 1

    async def test_dry_run(self):
        result = await send_with_retry(DryRunSender(), shop_id="s", buyer_id="b", text="t", idempotency_key="k")
        assert result.status == "dry_run"
