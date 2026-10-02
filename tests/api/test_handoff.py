"""人工坐席接口：/api/agent/* 与顾客侧转人工接口（handoff / tickets 服务为替身）。"""
import pytest

from app.core import handoff, tickets
from app.core.realtime import hub
from tests.api.test_auth import customer_headers, staff_headers


@pytest.fixture
def svc(monkeypatch):
    """按需替换 handoff / tickets.backend 的函数：svc.set("accept", return_value=...)。"""
    from unittest.mock import AsyncMock

    class Svc:
        def set(self, name, target=handoff, **kwargs):
            mock = AsyncMock(**kwargs)
            monkeypatch.setattr(target, name, mock)
            setattr(self, name, mock)
            return mock

        def ticket(self, name, **kwargs):
            return self.set(name, target=tickets.backend, **kwargs)

    return Svc()


class TestAgentPermissions:
    @pytest.mark.parametrize("method,path", [
        ("GET", "/api/agent/conversations"),
        ("POST", "/api/agent/conversations/1/accept"),
        ("POST", "/api/agent/tickets"),
    ])
    def test_reviewer_forbidden(self, anon_client, method, path):
        assert anon_client.request(method, path, json={}, headers=staff_headers("reviewer")).status_code == 403

    @pytest.mark.parametrize("role", ["agent", "admin"])
    def test_agent_and_admin_allowed(self, anon_client, svc, role):
        svc.set("list_for_staff", return_value=[])
        response = anon_client.get("/api/agent/conversations", params={"view": "queued"}, headers=staff_headers(role, "carol"))
        assert response.status_code == 200
        assert svc.list_for_staff.await_args.args == ("queued", "carol")


class TestAgentConversations:
    @pytest.mark.parametrize("error,status", [
        (handoff.HandoffError("已由 bob 接待"), 409),
        (handoff.HandoffForbidden("由 bob 接待"), 403),
        (LookupError("会话不存在"), 404),
        (RuntimeError("db"), 503),
    ])
    def test_error_mapping(self, client, svc, error, status):
        svc.set("accept", side_effect=error)
        response = client.post("/api/agent/conversations/3/accept")
        assert response.status_code == status

    def test_accept_uses_login_name(self, client, svc):
        svc.set("accept", return_value={"status": "active"})
        assert client.post("/api/agent/conversations/3/accept").json() == {"status": "active"}
        assert svc.accept.await_args.args[:2] == (3, "test-reviewer")

    def test_post_message(self, client, svc):
        svc.set("post", return_value={"role": "note"})
        client.post("/api/agent/conversations/3/messages", json={"text": "  备注 ", "kind": "note"})
        assert svc.post.await_args.args == (3, "test-reviewer", "备注", "note")

    @pytest.mark.parametrize("body", [{"text": ""}, {"text": "x" * 2001}, {"text": "hi", "kind": "shout"}])
    def test_post_validation(self, client, svc, body):
        svc.set("post")
        assert client.post("/api/agent/conversations/3/messages", json=body).status_code == 422

    def test_close_and_transfer_pass_admin_flag(self, client, svc):
        svc.set("close", return_value={})
        svc.set("transfer", return_value={})
        client.post("/api/agent/conversations/3/close")
        client.post("/api/agent/conversations/3/transfer", json={"to": "bob"})
        assert svc.close.await_args.kwargs == {"is_admin": True}
        assert svc.transfer.await_args.args == (3, "test-reviewer", "bob")

    def test_detail_includes_tickets(self, client, svc):
        svc.set("detail", return_value={"conversation_id": 3, "messages": []})
        svc.ticket("list", return_value=[{"ticket_no": "T1"}])
        assert client.get("/api/agent/conversations/3").json()["tickets"] == [{"ticket_no": "T1"}]
        assert svc.list.await_args.kwargs == {"conversation_id": 3, "limit": 20}

    def test_summary(self, client, svc):
        svc.set("counts", return_value={"queued": 2, "mine": 1, "active": 3})
        svc.ticket("stats", return_value={"待处理": 1})
        assert client.get("/api/agent/summary").json() == {"queued": 2, "mine": 1, "active": 3, "tickets": {"待处理": 1}}


class TestAgentTickets:
    BODY = {"conversation_id": 3, "ticket_type": "补发", "title": "肩带缺件", "description": "顾客反馈缺件"}

    def test_create_uses_conversation_owner(self, client, svc, monkeypatch):
        published = []
        monkeypatch.setattr(hub, "publish", lambda channel, event: published.append((channel, event)))
        svc.set("conversation_owner", return_value="u9")
        svc.ticket("create", return_value={"ticket_no": "T1", "conversation_id": 3})
        assert client.post("/api/agent/tickets", json=self.BODY).status_code == 200
        kwargs = svc.create.await_args.kwargs
        assert kwargs["user_id"] == "u9" and kwargs["actor"] == "test-reviewer" and kwargs["source"] == "staff"
        assert published == [("staff", {"type": "ticket", "ticket_no": "T1", "conversation_id": 3})]

    def test_create_unknown_conversation(self, client, svc):
        svc.set("conversation_owner", return_value=None)
        assert client.post("/api/agent/tickets", json=self.BODY).status_code == 404

    def test_create_rejects_unknown_type(self, client, svc):
        assert client.post("/api/agent/tickets", json={**self.BODY, "ticket_type": "退钱"}).status_code == 422

    def test_transition_conflict(self, client, svc):
        svc.ticket("transition", side_effect=tickets.TicketError("工单不能从「待处理」改为「已解决」"))
        response = client.post("/api/agent/tickets/T1/status", json={"status": "已解决"})
        assert response.status_code == 409 and "不能从" in response.json()["detail"]

    def test_missing_ticket(self, client, svc):
        svc.ticket("get", return_value=None)
        assert client.get("/api/agent/tickets/T404").status_code == 404


class TestCustomerHandoff:
    def test_status_defaults_to_ai(self, client, svc):
        svc.set("customer_status", return_value=None)
        assert client.get("/api/conversations/5/handoff").json() == {"status": "ai"}
        assert svc.customer_status.await_args.args == (5, "u1")

    def test_other_customer_gets_404(self, client, svc):
        svc.set("customer_status", side_effect=LookupError())
        assert client.get("/api/conversations/5/handoff").status_code == 404

    def test_request_and_cancel(self, client, svc):
        svc.set("request", return_value={"status": "queued", "position": 1})
        svc.set("cancel", side_effect=handoff.HandoffError("客服已接入，不能取消排队"))
        assert client.post("/api/conversations/5/handoff").json()["status"] == "queued"
        assert svc.request.await_args.args == (5, "u1", "customer_request")
        assert client.post("/api/conversations/5/handoff/cancel").status_code == 409

    def test_events_checks_ownership(self, client, repo):
        repo.set("get_conversation", return_value=None)
        assert client.get("/api/conversations/5/events").status_code == 404

    def test_staff_token_cannot_request_handoff(self, anon_client):
        assert anon_client.post("/api/conversations/5/handoff", headers=staff_headers()).status_code == 401

    def test_customer_token_cannot_use_agent_api(self, anon_client):
        assert anon_client.get("/api/agent/conversations", headers=customer_headers()).status_code == 401
