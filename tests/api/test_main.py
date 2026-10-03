"""app.main：健康检查、前端入口与 lifespan 装配（MCP、检查点、Langfuse 均为替身）。"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.core import observability


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"


def test_index_serves_built_frontend(client, monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>AssistFlow</title>", encoding="utf-8")
    monkeypatch.setattr(main, "WEB_DIST", tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"


def test_index_explains_missing_build(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "WEB_DIST", tmp_path / "missing")
    response = client.get("/")
    assert response.status_code == 503
    assert "npm run build" in response.text


@pytest.mark.parametrize("path", ["/admin", "/observability", "/kb", "/v2/", "/api/chat"])
def test_legacy_pages_removed(client, path):
    assert client.get(path).status_code in {404, 405}


def test_lifespan_wires_runtime_and_cleans_up(monkeypatch, tmp_path):
    services = SimpleNamespace()
    discover = AsyncMock(return_value=(services, [{"server": "logistics", "code": "discovery_failed"}]))
    monkeypatch.setattr(main, "make_services_with_mcp", discover)
    monkeypatch.setattr(main.settings, "mcp_logistics_url", "http://mcp.invalid/logistics")
    monkeypatch.setattr(main.settings, "mcp_aftersales_url", "  ")
    langfuse = object()
    monkeypatch.setattr(main, "create_langfuse_client", lambda settings: langfuse)
    closed = AsyncMock()
    monkeypatch.setattr(main, "close_langfuse_client", closed)
    summaries_closed = AsyncMock()
    monkeypatch.setattr(main, "close_persisted_summaries", summaries_closed)
    runtime = object()
    opened = []

    @asynccontextmanager
    async def persistent_runtime(svc, path):
        opened.append((svc, path))
        yield runtime

    monkeypatch.setattr(main, "persistent_runtime", persistent_runtime)
    monkeypatch.setattr(main.settings, "graph_checkpoint_path", str(tmp_path / "checkpoints.sqlite"))

    with TestClient(main.app) as client:
        assert client.app.state.graph_runtime is runtime
        assert client.app.state.langfuse_client is langfuse
        assert observability._default_trace_sink is main.trace_repo.insert_trace_span

    transport, servers = discover.await_args.args
    assert servers == ["logistics"]
    assert transport._url("logistics") == "http://mcp.invalid/logistics"
    assert services.audit_sink is main.trace_repo.insert_tool_audit
    assert opened == [(services, main.settings.graph_checkpoint_path)]
    summaries_closed.assert_awaited_once()
    closed.assert_awaited_once_with(langfuse)
    assert main.app.state.graph_runtime is None
    assert observability._default_trace_sink is None


def test_lifespan_refuses_second_process(monkeypatch, tmp_path):
    from app.core.instance_lock import InstanceLockError, single_instance

    monkeypatch.setattr(main.settings, "graph_checkpoint_path", str(tmp_path / "checkpoints.sqlite"))
    with single_instance(str(tmp_path / "checkpoints.sqlite.lock")):
        with pytest.raises(InstanceLockError, match="--workers"):
            with TestClient(main.app):
                pass
