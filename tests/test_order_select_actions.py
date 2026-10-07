"""
测试订单选择的HTTP流和数据持久化
覆盖选择/取消的转发、权限检查和保存失败处理
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import actions, graph_chat


@pytest.mark.parametrize("cancelled", [False, True])
def test_selection_http_forwards_choice_after_saving(monkeypatch, cancelled):
    """测试订单选择HTTP接口：保存后转发用户选择到图引擎"""
    calls = []
    async def stream(query, user, conversation, *, resume):
        calls.append((query, user, conversation, resume))
        yield {"delta": "完成"}
        yield {"event": "done"}
        yield {"event": "end"}
    runtime = SimpleNamespace(stream_turn=stream)
    saved = AsyncMock()
    scheduled = Mock()
    monkeypatch.setattr(graph_chat, "_persist_graph_messages", saved)
    monkeypatch.setattr(graph_chat, "schedule_persisted_summary", scheduled)
    monkeypatch.setattr(actions.conversation_repo, "get_conversation", AsyncMock(return_value=object()))
    app = FastAPI()
    app.include_router(actions.router)
    app.state.graph_runtime = runtime
    choice = {"cancelled": True} if cancelled else {"order_id": "ORD-1001"}
    payload = {"conversation_id": 1, "user_id": "u1", "request_id": "r1", **choice}
    with TestClient(app) as client:
        response = client.post("/api/actions/select-order", json=payload)
    assert response.status_code == 200
    assert calls == [("", "u1", "1", {"kind": "select_order", "request_id": "r1", "cancelled": cancelled, **choice})]
    saved.assert_awaited_once_with(runtime, "u1", 1)
    scheduled.assert_called_once_with("u1", 1, graph_chat.summarize_dialog)
    assert '"event": "done"' in response.text
    assert response.text.count('[DONE]') == 1


def test_other_conversation_cannot_resume(monkeypatch):
    """测试权限检查：用户不能恢复其他人的会话"""
    monkeypatch.setattr(actions.conversation_repo, "get_conversation", AsyncMock(return_value=None))
    stream = Mock()
    app = FastAPI()
    app.include_router(actions.router)
    app.state.graph_runtime = SimpleNamespace(stream_turn=stream)
    with TestClient(app) as client:
        response = client.post('/api/actions/select-order', json={
            "conversation_id": 1, "user_id": "u2", "request_id": "r1", "order_id": "ORD-1001",
        })
    assert response.status_code == 404
    stream.assert_not_called()


def test_save_failure_does_not_emit_success(monkeypatch):
    """测试保存失败处理：持久化失败时不输出成功事件"""
    async def stream(*args, **kwargs):
        yield {"delta": "完成"}
        yield {"event": "done"}
        yield {"event": "end"}
    saved = AsyncMock(side_effect=RuntimeError("private"))
    scheduled = Mock()
    monkeypatch.setattr(graph_chat, "_persist_graph_messages", saved)
    monkeypatch.setattr(graph_chat, "schedule_persisted_summary", scheduled)
    request = actions.SelectOrderRequest(conversation_id=1, user_id="u1", request_id="r1", cancelled=True)
    runtime = SimpleNamespace(stream_turn=stream)
    async def run():
        return ''.join([frame async for frame in actions.stream_order_selection(request, runtime)])

    output = asyncio.run(run())
    saved.assert_awaited_once_with(runtime, "u1", 1)
    scheduled.assert_not_called()
    assert '"event": "error"' in output
    assert '订单选择或消息保存失败，请检查当前待处理状态' in output
    assert '"event": "done"' not in output
    # 文字实时发出后无法撤回；保存失败仍必须不发 done，并以 error/[DONE] 收尾。
    assert output.startswith('data: {"delta": "完成"}\n\n')
    assert output.count('"delta"') == 1
    assert "private" not in output
    assert output.count('[DONE]') == 1


@pytest.mark.parametrize("cancelled", [False, True])
def test_selection_stream_resumes_real_graph_and_persists_messages(monkeypatch, cancelled):
    """真实主图恢复选单，验证共享后台任务不会与运行时的会话锁死锁。"""
    from app.core.intent import Intent
    from tests.test_graph_flow import chat, database, events
    from tests.test_graph_integration import fake_services, runtime

    scheduled = Mock()
    monkeypatch.setattr(graph_chat, "schedule_graph_summary", scheduled)

    async def run():
        async with database(monkeypatch) as cid:
            s = fake_services(Intent.REFUND)
            r = runtime(s)
            initial = events(await chat(r, cid, "我要退款"))
            card = initial[-1]
            assert card["event"] == "interrupt"
            before = await r.get_state("u1", cid)
            request = actions.SelectOrderRequest(
                user_id="u1", conversation_id=cid, request_id=card["request_id"],
                cancelled=cancelled, order_id=None if cancelled else "ORD-1001",
            )
            async def collect():
                return [frame async for frame in actions.stream_order_selection(request, r)]

            frames = await asyncio.wait_for(collect(), timeout=2)
            emitted = events(frames)
            snapshot = await r.get_state("u1", cid)
            assert not snapshot.next
            assert await r.pending_interrupt("u1", cid) is None
            assert [event["name"] for event in emitted if event.get("event") == "node"] == snapshot.values["trace"][len(before.values["trace"]):]
            assert [event for event in emitted if "delta" in event] == [{"delta": snapshot.values["answer"]}]
            assert emitted[-1] == {"event": "done", "conversation_id": cid,
                                   "request_id": card["request_id"], "message_id": snapshot.values["message_id"]}
            assert snapshot.values["message_id"] == (None if cancelled else f"msg_{cid}_{card['request_id']}")
            assert frames[-1] == "data: [DONE]\n\n"
            records = await graph_chat.conversation_repo.list_messages(cid)
            assert [record.role for record in records] == ["user", "graph_sync", "assistant"]
            assert records[-1].content == snapshot.values["answer"]
            scheduled.assert_called_once_with("u1", cid)
            s.agent.assert_not_awaited()
    asyncio.run(run())
