"""渠道启动与关闭：注册订单来源和坐席回复回调，退出时撤销。"""
from app.channels import service
from app.channels.sender import BridgeSender, DryRunSender
from app.config import settings
from app.core import realtime
from app.tools import orders


async def test_disabled_does_nothing(monkeypatch):
    monkeypatch.setattr(settings, "pdd_enabled", False)
    async with service.running(lambda: None) as dispatcher:
        assert dispatcher is None and service.dispatcher is None


async def test_lifecycle(monkeypatch, db):
    monkeypatch.setattr(settings, "pdd_enabled", True)
    monkeypatch.setattr(settings, "pdd_bridge_secret", "z" * 32)
    monkeypatch.setattr(settings, "pdd_bridge_send_url", "")
    async with service.running(lambda: None) as dispatcher:
        assert service.dispatcher is dispatcher and isinstance(dispatcher.sender, DryRunSender)
        assert dispatcher.on_publish in realtime.hub._listeners
        assert orders.provider_for_user("pdd-x") is not None
    assert service.dispatcher is None
    assert dispatcher.on_publish not in realtime.hub._listeners
    assert orders.provider_for_user("pdd-x") is None


def test_bridge_sender_when_url_set(monkeypatch):
    monkeypatch.setattr(settings, "pdd_bridge_secret", "z" * 32)
    monkeypatch.setattr(settings, "pdd_bridge_send_url", "https://bridge.example/send")
    assert isinstance(service.make_sender(), BridgeSender)
