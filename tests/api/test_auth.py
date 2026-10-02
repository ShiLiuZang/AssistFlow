"""认证与授权：令牌、密码、登录接口、路由鉴权清单、角色矩阵与限流。"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest

from app.config import settings
from app.core import auth
from app.main import app

PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/config"),
    ("POST", "/api/auth/dev/customer-token"),
}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def staff_headers(role="admin", username="alice"):
    return bearer(auth.issue_staff_token(username, role))


def customer_headers(user_id="u1"):
    return bearer(auth.issue_customer_token(user_id))


class TestPasswords:
    def test_roundtrip(self):
        stored = auth.hash_password("s3cret")
        assert stored.startswith("scrypt$") and auth.verify_password("s3cret", stored)
        assert not auth.verify_password("wrong", stored)

    def test_salted(self):
        assert auth.hash_password("same") != auth.hash_password("same")

    @pytest.mark.parametrize("stored", ["", "plain", "md5$aa$bb", "scrypt$zz$bb"])
    def test_malformed_hash_never_matches(self, stored):
        assert not auth.verify_password("x", stored)


class TestTokens:
    async def test_customer_roundtrip(self):
        token = auth.issue_customer_token("u9")
        assert await auth.current_customer(SimpleNamespace(credentials=token)) == "u9"

    async def test_staff_roundtrip(self):
        staff = await auth.current_staff(SimpleNamespace(credentials=auth.issue_staff_token("bob", "reviewer")))
        assert staff == auth.Staff("bob", "reviewer")

    @pytest.mark.parametrize("make", [
        lambda: auth.issue_staff_token("bob", "admin"),  # 员工令牌不能当顾客令牌
        lambda: jwt.encode({"typ": "customer", "sub": "u1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
                           settings.customer_token_secret, algorithm="HS256"),  # 已过期
        lambda: jwt.encode({"typ": "customer", "sub": "u1", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                           "another-secret-" + "z" * 32, algorithm="HS256"),  # 签名不对
        lambda: jwt.encode({"typ": "customer", "sub": "u1"}, settings.customer_token_secret, algorithm="HS256"),  # 缺 exp
        lambda: jwt.encode({"typ": "customer", "sub": " ", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                           settings.customer_token_secret, algorithm="HS256"),  # 空身份
        lambda: "not-a-jwt",
    ])
    async def test_customer_rejects(self, make):
        with pytest.raises(auth.HTTPException) as info:
            await auth.current_customer(SimpleNamespace(credentials=make()))
        assert info.value.status_code == 401

    async def test_customer_token_is_not_staff_token(self):
        with pytest.raises(auth.HTTPException) as info:
            await auth.current_staff(SimpleNamespace(credentials=auth.issue_customer_token("u1")))
        assert info.value.status_code == 401

    async def test_unknown_role_rejected(self):
        token = jwt.encode({"typ": "staff", "sub": "x", "role": "root", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                           settings.auth_secret, algorithm="HS256")
        with pytest.raises(auth.HTTPException):
            await auth.current_staff(SimpleNamespace(credentials=token))

    async def test_missing_credentials(self):
        with pytest.raises(auth.HTTPException) as info:
            await auth.current_customer(None)
        assert info.value.status_code == 401


class TestConfiguration:
    def test_rejects_short_secret_outside_dev_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_secret", "short")
        with pytest.raises(auth.AuthConfigError):
            auth.check_configuration()

    def test_dev_mode_generates_stable_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_secret", "")
        monkeypatch.setattr(settings, "auth_dev_mode", True)
        monkeypatch.setattr(auth, "_dev_secrets", {})
        auth.check_configuration()
        token = auth.issue_staff_token("dev", "admin")
        assert jwt.decode(token, auth._dev_secrets["auth_secret"], algorithms=["HS256"])["sub"] == "dev"


@pytest.fixture
def staff_repo(repo):
    user = SimpleNamespace(id=1, username="alice", password_hash=auth.hash_password("pw"), role="reviewer", active=True)
    repo.set("get_staff_user", return_value=user)
    repo.set("touch_staff_login")
    repo.user = user
    return repo


class TestLogin:
    def test_success(self, anon_client, staff_repo):
        body = anon_client.post("/api/auth/login", json={"username": "alice", "password": "pw"}).json()
        assert (body["username"], body["role"], body["token_type"]) == ("alice", "reviewer", "bearer")
        assert anon_client.get("/api/auth/me", headers=bearer(body["access_token"])).json() == {"username": "alice", "role": "reviewer"}
        staff_repo.touch_staff_login.assert_awaited_once_with(1)

    @pytest.mark.parametrize("change,password", [
        (lambda r: None, "bad"),  # 密码错
        (lambda r: setattr(r.get_staff_user, "return_value", None), "pw"),  # 用户不存在
        (lambda r: setattr(r.user, "active", False), "pw"),  # 已停用
        (lambda r: setattr(r.user, "role", "root"), "pw"),  # 角色无效
    ])
    def test_failures_share_one_message(self, anon_client, staff_repo, change, password):
        change(staff_repo)
        response = anon_client.post("/api/auth/login", json={"username": "alice", "password": password})
        assert (response.status_code, response.json()["detail"]) == (401, "用户名或密码错误")

    def test_repository_down(self, anon_client, repo):
        repo.set("get_staff_user", side_effect=RuntimeError())
        assert anon_client.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code == 503

    def test_touch_failure_does_not_block_login(self, anon_client, staff_repo):
        staff_repo.touch_staff_login.side_effect = RuntimeError()
        assert anon_client.post("/api/auth/login", json={"username": "alice", "password": "pw"}).status_code == 200

    def test_rate_limited_per_ip(self, anon_client, staff_repo, monkeypatch):
        monkeypatch.setattr(settings, "rate_login_per_minute", 3)
        codes = [anon_client.post("/api/auth/login", json={"username": "alice", "password": "bad"}).status_code for _ in range(4)]
        assert codes == [401, 401, 401, 429]


class TestDevCustomerToken:
    def test_hidden_outside_dev_mode(self, anon_client):
        assert anon_client.post("/api/auth/dev/customer-token", json={"user_id": "u1"}).status_code == 404
        assert anon_client.get("/api/auth/config").json() == {"dev_mode": False}

    def test_issues_usable_token(self, anon_client, repo, monkeypatch):
        monkeypatch.setattr(settings, "auth_dev_mode", True)
        token = anon_client.post("/api/auth/dev/customer-token", json={"user_id": "u7"}).json()["access_token"]
        repo.set("list_conversations", return_value=[])
        assert anon_client.get("/api/conversations", headers=bearer(token)).status_code == 200
        assert repo.list_conversations.await_args.args == ("u7",)

    @pytest.mark.parametrize("user_id", ["", "a b", "x" * 65])
    def test_validates_user_id(self, anon_client, monkeypatch, user_id):
        monkeypatch.setattr(settings, "auth_dev_mode", True)
        assert anon_client.post("/api/auth/dev/customer-token", json={"user_id": user_id}).status_code == 422


def api_routes():
    # 以 OpenAPI 文档为准：新增接口会自动进入清单
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if (method.upper(), path) not in PUBLIC:
                yield method.upper(), path


ROUTES = sorted(set(api_routes()))


def concrete(path):
    return path.replace("{name}", "kb-preview").replace("{source_ref}", "returns-policy.md").replace("{", "").replace("}", "") \
        .replace("review_id", "1").replace("conversation_id", "1").replace("chunk_id", "1").replace("candidate_id", "1")


class TestRouteInventory:
    def test_inventory_is_not_empty(self):
        assert len(ROUTES) > 40

    @pytest.mark.parametrize("method,path", ROUTES)
    def test_requires_token(self, anon_client, method, path):
        assert anon_client.request(method, concrete(path), json={}).status_code == 401

    @pytest.mark.parametrize("method,path", ROUTES)
    def test_wrong_kind_of_token_rejected(self, anon_client, method, path):
        customer_route = path.startswith(("/api/graph-chat", "/api/actions", "/api/conversations", "/api/feedback"))
        headers = staff_headers() if customer_route else customer_headers()
        assert anon_client.request(method, concrete(path), json={}, headers=headers).status_code == 401


class TestRoleMatrix:
    @pytest.mark.parametrize("method,path,role,allowed", [
        ("POST", "/api/review/1/publish", "agent", False),
        ("POST", "/api/review/1/reject", "agent", False),
        ("POST", "/api/review/process", "agent", False),
        ("POST", "/api/kb/staging/approve", "agent", False),
        ("POST", "/api/kb/ingest", "reviewer", False),
        ("POST", "/api/kb/vectorize", "reviewer", False),
        ("POST", "/api/kb/preview", "reviewer", False),
        ("POST", "/api/jobs/kb-preview", "reviewer", False),
        ("POST", "/api/jobs/kb-preview/stop", "reviewer", False),
        ("POST", "/api/knowledge/evaluate", "reviewer", False),
        ("POST", "/api/review/1/reject", "reviewer", True),
        ("POST", "/api/kb/staging/reject", "reviewer", True),
    ])
    def test_matrix(self, anon_client, repo, method, path, role, allowed):
        # 放行后的业务调用一律失败，避免连接真实数据库；这里只关心是否被 403 拦下
        for name in ("reject_review", "list_staging_by_ids", "set_staging_status"):
            repo.set(name, side_effect=LookupError("stub"))
        status = anon_client.request(method, path, json={}, headers=staff_headers(role)).status_code
        assert (status != 403) is allowed

    @pytest.mark.parametrize("path", ["/api/admin/overview", "/api/jobs", "/api/review/stats", "/api/kb/chunks"])
    def test_agent_can_read(self, anon_client, repo, path, monkeypatch):
        for name in ("flywheel_stats", "list_knowledge_chunks"):
            repo.set(name, side_effect=RuntimeError())
        assert anon_client.get(path, headers=staff_headers("agent")).status_code not in {401, 403}

    def test_reviewer_name_comes_from_token(self, anon_client, repo):
        repo.set("reject_review", return_value={"id": 1, "question": "q", "suggestion": "s", "status": "rejected"})
        anon_client.post("/api/review/1/reject", headers=staff_headers("reviewer", "carol"))
        assert repo.reject_review.await_args.args == (1, "carol")


class TestCustomerIdentity:
    def test_forged_user_id_is_ignored(self, anon_client, repo):
        repo.set("get_conversation", return_value=None)
        response = anon_client.get("/api/conversations/5/messages", params={"user_id": "victim"}, headers=customer_headers("attacker"))
        assert response.status_code == 404
        assert repo.get_conversation.await_args.args == (5, "attacker")

    def test_feedback_uses_token_identity(self, anon_client, repo):
        repo.set("get_conversation", return_value=None)
        body = {"user_id": "victim", "conversation_id": 5, "message_id": "m", "rating": "up"}
        assert anon_client.post("/api/feedback", json=body, headers=customer_headers("attacker")).status_code == 404
        assert repo.get_conversation.await_args.args == (5, "attacker")

    def test_chat_rate_limit(self, anon_client, repo, monkeypatch):
        monkeypatch.setattr(settings, "rate_chat_per_minute", 2)
        app.state.graph_runtime = None  # 503 说明已经通过鉴权与限流
        codes = [anon_client.post("/api/graph-chat", json={"message": "hi"}, headers=customer_headers()).status_code for _ in range(3)]
        assert codes == [503, 503, 429]

    def test_rate_limit_is_per_customer(self, anon_client, monkeypatch):
        monkeypatch.setattr(settings, "rate_chat_per_minute", 1)
        assert anon_client.post("/api/graph-chat", json={"message": "hi"}, headers=customer_headers("a")).status_code == 503
        assert anon_client.post("/api/graph-chat", json={"message": "hi"}, headers=customer_headers("b")).status_code == 503
        assert anon_client.post("/api/graph-chat", json={"message": "hi"}, headers=customer_headers("a")).status_code == 429
