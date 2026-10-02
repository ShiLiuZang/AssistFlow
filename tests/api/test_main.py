"""app.main：健康检查、静态页面路由与 lifespan 装配（MCP、检查点、Langfuse 均为替身）。"""
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


@pytest.mark.parametrize("path", ["/", "/observability", "/admin"])
def test_main_pages(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", sorted(set(main.ADMIN_PAGES) - {"/rag-eval"}))
def test_admin_pages_not_cached(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("text/html")


def test_every_admin_page_file_exists():
    assert all((main.STATIC_DIR / name).is_file() for name in main.ADMIN_PAGES.values())


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

    with TestClient(main.app) as client:
        assert client.app.state.graph_runtime is runtime
        assert client.app.state.langfuse_client is langfuse
        assert observability._default_trace_sink is main.repository.insert_trace_span

    transport, servers = discover.await_args.args
    assert servers == ["logistics"]
    assert transport._url("logistics") == "http://mcp.invalid/logistics"
    assert services.audit_sink is main.repository.insert_tool_audit
    assert opened == [(services, main.settings.graph_checkpoint_path)]
    summaries_closed.assert_awaited_once()
    closed.assert_awaited_once_with(langfuse)
    assert main.app.state.graph_runtime is None
    assert observability._default_trace_sink is None
