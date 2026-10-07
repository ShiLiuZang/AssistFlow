"""V2 复用现有作业 API：替换进程启动与日志查询，不运行外部服务或命令。"""
import asyncio
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.conftest import ADMIN_HEADERS

from app.api import jobs as jobs_api


def test_vector_job_existing_route_and_whitelist(monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(jobs_api.jobs, "start", start)
    state = {"name": "kb-vectorize", "status": "running", "pid": 123,
             "started_at": "2026-10-01T00:10:00", "finished_at": None,
             "returncode": None, "log": "一次性测试日志"}
    monkeypatch.setattr(jobs_api.jobs, "status", lambda name, with_log=False: dict(state))

    async def run():
        app = FastAPI()
        app.include_router(jobs_api.router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS) as api:
            response = await api.post("/api/jobs/kb-vectorize")
            assert response.status_code == 200 and response.json()["status"] == "running"
            assert response.json()["log"] == "一次性测试日志"
            assert (await api.get("/api/jobs/kb-vectorize")).json()["status"] == "running"
            for method in (api.post, api.get):
                assert (await method("/api/jobs/not-registered")).status_code == 404
    asyncio.run(run())
    start.assert_awaited_once_with("kb-vectorize")


def test_running_job_conflict_preserves_existing_status(monkeypatch):
    start = AsyncMock(side_effect=RuntimeError("同一作业已经运行"))
    monkeypatch.setattr(jobs_api.jobs, "start", start)
    monkeypatch.setattr(jobs_api.jobs, "status", lambda name, with_log=False: {
        "name": name, "status": "running", "pid": 123, "log": "仍在执行",
    })

    async def run():
        app = FastAPI()
        app.include_router(jobs_api.router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS) as api:
            response = await api.post("/api/jobs/kb-vectorize")
            assert response.status_code == 409 and isinstance(response.json()["detail"], str)
            state = (await api.get("/api/jobs/kb-vectorize")).json()
            assert state["status"] == "running" and state["log"] == "仍在执行"
    asyncio.run(run())
    start.assert_awaited_once_with("kb-vectorize")
