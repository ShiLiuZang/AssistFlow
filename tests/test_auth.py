"""鉴权验收：签名、身份隔离、各 API 拒绝路径与公开页面。"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import actions, extract, graph_chat
from app.config import settings
from app.core import auth
from app.db import conversation_repo, flywheel_repo
from app.main import ADMIN_PAGES, app
from app.schemas.extract import AfterSalesTicket
from tests.conftest import ADMIN_HEADERS, visitor_headers
from tests.test_kb_read_queries import database


VISITOR_CASES = [
    ("POST", "/api/graph-chat", {"message": "你好"}),
    ("GET", "/api/actions/pending?conversation_id=7", None),
    ("POST", "/api/actions/resume", {"conversation_id": 7, "tool_call_id": "c1", "confirmed": True}),
    ("POST", "/api/actions/select-order", {"conversation_id": 7, "request_id": "r1", "cancelled": True}),
    ("GET", "/api/conversations", None),
    ("GET", "/api/conversations/7/messages", None),
    ("POST", "/api/feedback", {"conversation_id": 7, "message_id": "m1", "rating": "up"}),
    ("POST", "/api/extract", {"text": "商品破损"}),
]


def api_routes(routes):
    """展开 FastAPI 的延迟 include_router，直接检查实际的路由依赖。"""
    for route in routes:
        if hasattr(route, "effective_route_contexts"):
            yield from (context for context in route.effective_route_contexts() if context.path.startswith("/api/"))
        elif getattr(route, "path", "").startswith("/api/"):
            yield route


ADMIN_ROUTES = [
    (method, route.path)
    for route in api_routes(app.routes)
    if any(dep.call is auth.require_admin for dep in route.dependant.dependencies)
    for method in sorted(route.methods)
]


def test_token_issue_verify_and_ttl(monkeypatch):
    monkeypatch.setattr(auth.time, "time", lambda: 1000)
    monkeypatch.setattr(settings, "visitor_token_ttl_days", 2)
    token, expires_at = auth.issue_visitor_token("visitor-a")
    assert expires_at == 1000 + 2 * 86400
    assert auth.verify_visitor_token(token) == "visitor-a"
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    assert payload == {"sub": "visitor-a", "exp": expires_at}


def test_token_tampering_expiry_and_rotated_key(monkeypatch):
    monkeypatch.setattr(auth.time, "time", lambda: 1000)
    token, expires_at = auth.issue_visitor_token("visitor-a")
    payload, signature = token.split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"sub": "visitor-b", "exp": expires_at}).encode()).rstrip(b"=").decode()
    for invalid in (f"{forged}.{signature}", f"{payload}.{'A' * 43}"):
        with pytest.raises(ValueError):
            auth.verify_visitor_token(invalid)
    monkeypatch.setattr(auth.time, "time", lambda: expires_at)
    with pytest.raises(ValueError):
        auth.verify_visitor_token(token)
    monkeypatch.setattr(auth.time, "time", lambda: 1000)
    monkeypatch.setattr(settings, "auth_secret", "another-key")
    with pytest.raises(ValueError):
        auth.verify_visitor_token(token)


@pytest.mark.parametrize("token", ["", "x", "x.y.z", "☃.x", "!.!", "e30=.e30=", "e30.e30"])
def test_malformed_tokens_are_rejected(token):
    with pytest.raises(ValueError):
        auth.verify_visitor_token(token)


@pytest.mark.parametrize("data", [[], {}, {"sub": "a"}, {"sub": "", "exp": 9999999999},
                                      {"sub": 1, "exp": 9999999999}, {"sub": "a", "exp": True},
                                      {"sub": "a", "exp": "9999999999"}])
def test_signed_invalid_payload_is_rejected(data):
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    signature = hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest()
    token = payload + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    with pytest.raises(ValueError):
        auth.verify_visitor_token(token)


def test_empty_secret_is_process_local_and_warning_has_no_key(monkeypatch, caplog):
    monkeypatch.setattr(settings, "auth_secret", "")
    monkeypatch.setattr(auth, "_process_secret", None)
    with caplog.at_level(logging.WARNING, logger="app.core.auth"):
        auth.initialize_auth()
        token, _ = auth.issue_visitor_token("a")
        auth.initialize_auth()
        assert auth.verify_visitor_token(token) == "a"
    assert len(caplog.records) == 1
    assert "重启后访客令牌失效" in caplog.text
    assert auth._process_secret.hex() not in caplog.text
    assert base64.urlsafe_b64encode(auth._process_secret).decode() not in caplog.text
    monkeypatch.setattr(auth, "_process_secret", None)
    with pytest.raises(ValueError):
        auth.verify_visitor_token(token)


def test_public_issuance_does_not_accept_client_identity():
    client = TestClient(app)
    response = client.post("/api/auth/visitor", json={"user_id": "victim"})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"user_id", "token", "expires_at"}
    assert data["user_id"].startswith("v_") and len(data["user_id"]) == 34
    assert auth.verify_visitor_token(data["token"]) == data["user_id"]
    assert data["user_id"] != "victim"
    assert client.post("/api/auth/visitor").json()["user_id"] != data["user_id"]


@pytest.mark.parametrize("method,url,body", VISITOR_CASES)
@pytest.mark.parametrize("authorization", [None, "Bearer invalid", "Basic wrong", "Bearer test-admin-placeholder"])
def test_visitor_api_requires_valid_token(method, url, body, authorization):
    response = TestClient(app).request(method, url, json=body,
                                       headers={"Authorization": authorization} if authorization else {})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("method,url,body", VISITOR_CASES)
def test_visitor_identity_mismatch_is_403(method, url, body):
    if method == "GET":
        url += ("&" if "?" in url else "?") + "user_id=victim"
    else:
        body = {**body, "user_id": "victim"}
    response = TestClient(app).request(method, url, json=body, headers=visitor_headers("a"))
    assert response.status_code == 403
    assert response.json() == {"detail": "user_id 与访客令牌不一致"}


@pytest.mark.parametrize("method,url,body", VISITOR_CASES)
@pytest.mark.parametrize("include_identity", [False, True])
def test_visitor_api_uses_token_identity(monkeypatch, method, url, body, include_identity):
    owner = AsyncMock(return_value=SimpleNamespace(id=7))
    create = AsyncMock(return_value=7)
    monkeypatch.setattr(conversation_repo, "get_conversation", owner)
    monkeypatch.setattr(conversation_repo, "create_conversation", create)
    monkeypatch.setattr(conversation_repo, "list_conversations", AsyncMock(return_value=[SimpleNamespace(id=7, created_at=datetime(2026, 1, 1))]))
    monkeypatch.setattr(conversation_repo, "list_dialog_messages", AsyncMock(return_value=[]))
    monkeypatch.setattr(conversation_repo, "list_messages", AsyncMock(return_value=[SimpleNamespace(tool_calls=[{"id": "c1", "name": "create_ticket"}])]))
    submit = AsyncMock(return_value=None)
    monkeypatch.setattr(flywheel_repo, "submit_feedback", submit)
    monkeypatch.setattr(app.state, "graph_runtime", SimpleNamespace(pending_interrupt=AsyncMock(return_value=None)), raising=False)

    captured = []
    async def stream(request, *args):
        captured.append(request.user_id)
        yield "data: [DONE]\n\n"
    monkeypatch.setattr(graph_chat, "stream_graph_chat", stream)
    monkeypatch.setattr(actions, "stream_ticket_decision", stream)
    monkeypatch.setattr(actions, "stream_order_selection", stream)
    result = AfterSalesTicket(order_id=None, request_type="投诉", expected_solution="处理破损")
    monkeypatch.setattr(extract, "get_chat_model", lambda: SimpleNamespace(with_structured_output=lambda *a, **kw: SimpleNamespace(ainvoke=AsyncMock(return_value=result))))
    if include_identity:
        if method == "GET":
            url += ("&" if "?" in url else "?") + "user_id=a"
        else:
            body = {**body, "user_id": "a"}
    response = TestClient(app).request(method, url, json=body, headers=visitor_headers("a"))
    assert response.status_code == 200
    for call in owner.await_args_list:
        assert call.args == (7, "a")
    for call in create.await_args_list:
        assert call.args == ("a",)
    if captured:
        assert captured == ["a"]
    if url.startswith("/api/feedback"):
        submit.assert_awaited_once_with(owner="a", conversation="7", message_id="m1", rating="up")
    if url.startswith("/api/conversations") and "/messages" not in url:
        conversation_repo.list_conversations.assert_awaited_once_with("a")


def test_visitor_cannot_read_other_visitors_conversation(monkeypatch):
    async def run():
        async with database(monkeypatch):
            cid = await conversation_repo.create_conversation("b")
            await conversation_repo.append_message(cid, "user", "private-b")
            client = TestClient(app)
            url = f"/api/conversations/{cid}/messages"
            response = await asyncio.to_thread(client.get, url, headers=visitor_headers("a"))
            assert response.status_code == 404
            assert "private-b" not in response.text
            spoof = await asyncio.to_thread(client.get, url + "?user_id=b", headers=visitor_headers("a"))
            assert spoof.status_code == 403
            own = await asyncio.to_thread(client.get, url, headers=visitor_headers("b"))
            assert own.status_code == 200 and own.json()[0]["content"] == "private-b"
            listed = await asyncio.to_thread(client.get, "/api/conversations", headers=visitor_headers("a"))
            assert listed.json() == []
    asyncio.run(run())


@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
def test_every_admin_api_rejects_missing_wrong_and_unconfigured_token(monkeypatch, method, url):
    client = TestClient(app)
    url = url.replace("{name}", "not-registered").replace("{review_id}", "1")
    for headers in ({}, {"Authorization": "Bearer wrong"}, visitor_headers("a")):
        response = client.request(method, url, headers=headers)
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
    monkeypatch.setattr(settings, "admin_token", "")
    response = client.request(method, url, headers=ADMIN_HEADERS)
    assert response.status_code == 503
    assert response.json() == {"detail": "未配置 ADMIN_TOKEN"}


def test_correct_admin_token_and_unicode_comparison():
    response = TestClient(app).get("/api/knowledge/cases", headers=ADMIN_HEADERS)
    assert response.status_code == 200 and response.json()["cases"]
    assert auth.require_admin("Bearer test-admin-placeholder") is None
    with pytest.raises(HTTPException) as exc:
        auth.require_admin("Bearer 错误令牌")
    assert exc.value.status_code == 401


@pytest.mark.parametrize("url", ["/", "/admin", "/observability", *ADMIN_PAGES, "/api/health", "/static/admin-auth.js"])
def test_pages_static_and_health_are_public(url):
    response = TestClient(app).get(url)
    assert response.status_code == 200
    if url in ["/", "/admin", "/observability", *ADMIN_PAGES]:
        assert response.headers["content-type"].startswith("text/html")


def test_api_public_whitelist_is_exact():
    public = set()
    for route in api_routes(app.routes):
        guards = {dep.call for dep in route.dependant.dependencies} & {auth.require_visitor, auth.require_admin}
        assert len(guards) <= 1
        if not guards:
            public.add(route.path)
    assert public == {"/api/health", "/api/auth/visitor"}
    assert len(ADMIN_ROUTES) == 34
