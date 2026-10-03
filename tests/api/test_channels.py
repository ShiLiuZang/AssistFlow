"""渠道接口：签名校验、开关、状态查询。"""
import json
import time
from unittest.mock import AsyncMock

import pytest

from app.channels import service
from app.channels.pinduoduo import bridge_signature
from app.config import settings
from tests.api.test_auth import staff_headers

SECRET = "b" * 32
PATH = "/api/channels/pinduoduo/events"
BODY = {"shop_id": "shop1", "events": [{"msg_id": "m1", "buyer_id": "buyer1", "text": "在吗"}]}


def signed(body: bytes, secret=SECRET, timestamp=None):
    timestamp = str(timestamp or int(time.time()))
    return {"X-AssistFlow-Timestamp": timestamp, "X-AssistFlow-Signature": bridge_signature(secret, timestamp, body),
            "Content-Type": "application/json"}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "pdd_enabled", True)
    monkeypatch.setattr(settings, "pdd_bridge_secret", SECRET)
    dispatcher = AsyncMock()
    dispatcher.receive.return_value = {"accepted": ["m1"], "duplicates": []}
    monkeypatch.setattr(service, "dispatcher", dispatcher)
    return dispatcher


class TestEvents:
    def test_disabled(self, anon_client):
        body = json.dumps(BODY).encode()
        assert anon_client.post(PATH, content=body, headers=signed(body)).status_code == 404

    def test_accepts_signed(self, anon_client, enabled):
        body = json.dumps(BODY).encode()
        response = anon_client.post(PATH, content=body, headers=signed(body))
        assert response.status_code == 202 and response.json() == {"accepted": ["m1"], "duplicates": []}
        payload = enabled.receive.await_args.args[0]
        assert payload.shop_id == "shop1" and payload.events[0].text == "在吗"

    @pytest.mark.parametrize("headers", [
        {},
        signed(b"other"),
        signed(json.dumps(BODY).encode(), secret="x" * 32),
        signed(json.dumps(BODY).encode(), timestamp=int(time.time()) - 600),
    ])
    def test_rejects_bad_signature(self, anon_client, enabled, headers):
        response = anon_client.post(PATH, content=json.dumps(BODY).encode(), headers=headers)
        assert response.status_code == 401
        enabled.receive.assert_not_awaited()

    def test_validates_payload(self, anon_client, enabled):
        body = json.dumps({"shop_id": "shop1", "events": []}).encode()
        assert anon_client.post(PATH, content=body, headers=signed(body)).status_code == 422

    def test_body_limit(self, anon_client, enabled):
        body = b"x" * (300 * 1024)
        assert anon_client.post(PATH, content=body, headers=signed(body)).status_code == 413


class TestStatus:
    def test_admin_only(self, anon_client):
        assert anon_client.get("/api/channels/status", headers=staff_headers("agent")).status_code == 403
        data = anon_client.get("/api/channels/status", headers=staff_headers("admin")).json()
        assert data["enabled"] is False and data["send_mode"] == "dry_run" and "stats" not in data


class TestConfiguration:
    def test_requires_secret_when_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "pdd_enabled", True)
        monkeypatch.setattr(settings, "pdd_bridge_secret", "short")
        with pytest.raises(service.ChannelConfigError):
            service.check_configuration()
        monkeypatch.setattr(settings, "pdd_enabled", False)
        service.check_configuration()
