"""拼多多：渠道桥签名、入站格式、话术规则、开放平台签名与订单查询、订单归属。"""
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.channels import pinduoduo, store
from app.channels.pinduoduo import PddClient, PddEvent, PddInbound, PddOrderProvider
from app.config import settings
from app.core.coref import entities
from app.graph import adapters
from app.tools import orders
from app.tools.context import ToolContext

ORDER = "231003-123456789012345"


class TestBridgeSignature:
    def test_roundtrip(self):
        body = b'{"a":1}'
        signature = pinduoduo.bridge_signature("k" * 32, "1700000000", body)
        assert pinduoduo.verify_bridge("k" * 32, "1700000000", signature, body, now=1700000100)
        assert pinduoduo.verify_bridge("k" * 32, "1700000000", signature.upper(), body, now=1700000100)

    def test_rejects_tampered_expired_or_missing(self):
        body = b'{"a":1}'
        signature = pinduoduo.bridge_signature("k" * 32, "1700000000", body)
        assert not pinduoduo.verify_bridge("k" * 32, "1700000000", signature, b'{"a":2}', now=1700000000)
        assert not pinduoduo.verify_bridge("j" * 32, "1700000000", signature, body, now=1700000000)
        assert not pinduoduo.verify_bridge("k" * 32, "1700000000", signature, body, now=1700000301)
        assert not pinduoduo.verify_bridge("k" * 32, None, signature, body)
        assert not pinduoduo.verify_bridge("k" * 32, "abc", signature, body)
        assert not pinduoduo.verify_bridge("", "1700000000", signature, body, now=1700000000)


class TestInbound:
    def test_event_text(self):
        assert pinduoduo.event_text(PddEvent(msg_id="1", buyer_id="b", text=" 在吗 ")) == "在吗"
        assert pinduoduo.event_text(PddEvent(msg_id="1", buyer_id="b", type="image")) is None
        assert pinduoduo.event_text(PddEvent(msg_id="1", buyer_id="b", type="text", text="")) is None
        goods = PddEvent(msg_id="1", buyer_id="b", type="goods", goods_name="保温杯", text="有现货吗")
        assert pinduoduo.event_text(goods) == "[咨询商品] 保温杯\n有现货吗"
        order = PddEvent(msg_id="1", buyer_id="b", type="order", order_sn=ORDER, goods_name="保温杯")
        assert pinduoduo.event_text(order) == f"[订单 {ORDER}] 保温杯"

    def test_validation(self):
        with pytest.raises(ValueError):
            PddInbound.model_validate({"shop_id": "s", "events": []})
        with pytest.raises(ValueError):
            PddEvent(msg_id="1", buyer_id="b", order_sn="ORD-1")


class TestSanitize:
    def test_removes_links_and_contacts(self):
        raw = "**退货**请看 https://evil.example/x 或加微信 abc12345，电话 13812345678，座机 021-12345678。"
        cleaned = pinduoduo.sanitize(raw)
        assert "http" not in cleaned and "abc12345" not in cleaned
        assert "13812345678" not in cleaned and "021-12345678" not in cleaned
        assert cleaned.startswith("退货请看")

    def test_keeps_order_numbers(self):
        assert ORDER in pinduoduo.sanitize(f"您的订单 {ORDER} 已发货")


class TestGateway:
    def test_sign(self):
        params = {"type": "pdd.order.information.get", "client_id": "abc", "timestamp": "1700000000",
                  "data_type": "JSON"}
        assert pinduoduo.gateway_sign(params, "testSecret") == "8BF6BD33BC7FF7C4A81C830504523BA9"

    @pytest.fixture
    def configured(self, monkeypatch):
        monkeypatch.setattr(settings, "pdd_client_id", "cid")
        monkeypatch.setattr(settings, "pdd_client_secret", "secret")
        monkeypatch.setattr(settings, "pdd_access_token", "token")

    async def test_order_info_request(self, configured):
        seen = {}

        def handler(request):
            params = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            seen.update(params)
            return httpx.Response(200, json={"order_info_get_response": {"order_info": {"order_status": 2}}})

        client = PddClient(transport=httpx.MockTransport(handler))
        assert await client.order_info(ORDER) == {"order_status": 2}
        assert seen["type"] == "pdd.order.information.get" and seen["order_sn"] == ORDER
        assert seen["client_id"] == "cid" and seen["access_token"] == "token" and seen["data_type"] == "JSON"
        sign = seen.pop("sign")
        assert sign == pinduoduo.gateway_sign(seen, "secret")

    async def test_error_response(self, configured):
        client = PddClient(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={"error_response": {"error_code": 10019, "error_msg": "access_token已过期"}})))
        with pytest.raises(pinduoduo.PddApiError) as error:
            await client.order_info(ORDER)
        assert error.value.code == 10019

    def test_status_text(self):
        assert pinduoduo.order_status_text({"order_status": 1, "refund_status": 1}) == "待发货"
        assert pinduoduo.order_status_text({"order_status": 3, "refund_status": 4}) == "已签收，退款成功"
        assert pinduoduo.order_status_text({}) == "状态未知"


class FakeClient:
    def __init__(self, info=None, error=None, configured=True):
        self.info, self.error, self.configured = info, error, configured

    async def order_info(self, order_sn):
        if self.error:
            raise self.error
        return self.info


class TestOrderProvider:
    async def test_only_attested_orders(self, db):
        provider = PddOrderProvider(FakeClient(info={"order_status": 2, "item_list": [{"goods_name": "保温杯 500ml"}],
                                                     "tracking_number": "SF123"}))
        assert await provider.get(ORDER) is None
        assert await store.attest_order("pinduoduo", ORDER, "pdd-a", "保温杯")
        assert await provider.get(ORDER) == {"order_id": ORDER, "user_id": "pdd-a", "product_name": "保温杯 500ml",
                                             "status": "已发货待签收", "tracking_number": "SF123"}
        # 同一订单不能再登记到别的买家名下
        assert not await store.attest_order("pinduoduo", ORDER, "pdd-b")
        assert (await provider.get(ORDER))["user_id"] == "pdd-a"
        assert await provider.list_for_user("pdd-a") == [
            {"order_id": ORDER, "user_id": "pdd-a", "product_name": "保温杯", "status": ""}]
        assert await provider.list_for_user("pdd-b") == []

    async def test_api_failure_or_unconfigured_falls_back(self, db):
        await store.attest_order("pinduoduo", ORDER, "pdd-a", "保温杯")
        for client in (FakeClient(error=RuntimeError("down")), FakeClient(configured=False)):
            order = await PddOrderProvider(client).get(ORDER)
            assert order["product_name"] == "保温杯" and order["status"] == "暂时查不到状态"

    def test_claims(self):
        provider = PddOrderProvider(FakeClient())
        assert provider.handles_order(ORDER) and not provider.handles_order("ORD-1001")
        assert provider.handles_user("pdd-abc") and not provider.handles_user("u1")


class TestGraphIntegration:
    @pytest.fixture
    def provider(self, db):
        provider = PddOrderProvider(FakeClient(info={"order_status": 1}))
        orders.register_provider(provider)
        yield provider
        orders.unregister_provider(provider)

    def test_coref_extracts_pdd_order(self):
        assert entities(f"我的订单{ORDER}怎么还没发") == [ORDER]
        assert entities("ORD-1001 和 MH-X1") == ["ORD-1001", "MH-X1"]

    async def test_order_tool_checks_owner(self, provider):
        await store.attest_order("pinduoduo", ORDER, "pdd-a", "保温杯")
        mine = await adapters.order_tool({"order_id": ORDER}, ToolContext(user_id="pdd-a", conversation_id="1"), "c1")
        assert mine == {"found": True, "order_id": ORDER, "product_name": "保温杯", "status": "待发货"}
        other = await adapters.order_tool({"order_id": ORDER}, ToolContext(user_id="pdd-b", conversation_id="1"), "c1")
        assert other["found"] is False and other["code"] == "order_not_owned"

    async def test_services_use_provider(self, provider):
        await store.attest_order("pinduoduo", ORDER, "pdd-a", "保温杯")
        assert [o["order_id"] for o in await adapters.list_orders("pdd-a")] == [ORDER]
        assert (await adapters.get_verified_order(ORDER))["user_id"] == "pdd-a"
        # 演示数据不受影响
        assert (await adapters.get_verified_order("ORD-1001"))["user_id"] == "u1"
        assert [o["order_id"] for o in await adapters.list_orders("u1")] == ["ORD-1001"]
