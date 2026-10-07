"""
测试API基础功能
覆盖请求验证、结构化提取、异常处理和错误信息脱敏
"""
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from tests.conftest import visitor_headers
from app.main import app
from app.schemas.extract import AfterSalesTicket


def test_request_validation_precedes_external_calls():
    """测试请求验证：空消息和空文本应在调用外部服务前拒绝"""
    client = TestClient(app, headers=visitor_headers())
    assert client.post("/api/graph-chat", json={"user_id": "u1", "message": ""}).status_code == 422
    assert client.post("/api/extract", json={"text": ""}).status_code == 422


def test_extract_nullable_order_and_safe_failure(monkeypatch):
    """测试结构化提取：支持可空字段，异常时返回502且脱敏错误信息"""
    api = importlib.import_module("app.api.extract")
    invoke = AsyncMock(return_value=AfterSalesTicket(order_id=None, request_type="投诉", expected_solution="处理破损"))
    monkeypatch.setattr(api, "get_chat_model", lambda: SimpleNamespace(
        with_structured_output=lambda *a, **kw: SimpleNamespace(ainvoke=invoke)))
    client = TestClient(app, headers=visitor_headers())
    response = client.post("/api/extract", json={"text": "收到破损商品"})
    assert response.status_code == 200
    assert response.json()["order_id"] is None
    invoke.side_effect = RuntimeError("private upstream error")
    response = client.post("/api/extract", json={"text": "收到破损商品"})
    assert response.status_code == 502
    assert "private" not in response.text
