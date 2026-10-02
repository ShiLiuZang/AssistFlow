"""接口测试共用：真实 FastAPI 应用（不跑 lifespan，不连 MySQL/Milvus/模型）与 repository 替身。"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db import repository as repository_module
from app.main import app


@pytest.fixture
def client():
    """不进入 lifespan，避免启动时连接 MCP、SQLite 检查点等外部资源。"""
    app.state.graph_runtime = None
    yield TestClient(app)
    app.state.graph_runtime = None


@pytest.fixture
def repo(monkeypatch):
    """按需替换 app.db.repository 中的函数：repo.set(name, return_value=...)。"""

    class Repo:
        def set(self, name, **kwargs):
            mock = AsyncMock(**kwargs)
            monkeypatch.setattr(repository_module, name, mock)
            setattr(self, name, mock)
            return mock

    return Repo()


def conversation(conversation_id=7, summary_text="", summary_upto=0):
    return SimpleNamespace(id=conversation_id, summary_text=summary_text, summary_upto=summary_upto)


def sse_frames(text):
    """把 SSE 响应拆成 (event, data) 列表；data 为 JSON 时解析成对象。"""
    frames = []
    for block in text.strip().split("\n\n"):
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = line[len("data: "):]
        if data is not None and data.startswith("{"):
            data = json.loads(data)
        frames.append((event, data))
    return frames
