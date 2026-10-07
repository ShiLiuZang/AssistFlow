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

from app.api import actions


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
    monkeypatch.setattr(actions, "_persist_graph_messages", saved)
    monkeypatch.setattr(actions.repository, "get_conversation", AsyncMock(return_value=object()))
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
    assert '"event": "done"' in response.text
    assert response.text.count('[DONE]') == 1


def test_other_conversation_cannot_resume(monkeypatch):
    """测试权限检查：用户不能恢复其他人的会话"""
    monkeypatch.setattr(actions.repository, "get_conversation", AsyncMock(return_value=None))
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
    monkeypatch.setattr(actions, "_persist_graph_messages", saved)
    monkeypatch.setattr(actions, "schedule_persisted_summary", scheduled)
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
    assert '"delta"' not in output
    assert "private" not in output
    assert output.count('[DONE]') == 1
