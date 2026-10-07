"""
测试会话流编排与数据库持久化
覆盖意图路由、工具调用、消息存储、错误处理和恢复流程
"""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api.graph_chat import stream_graph_chat
from app.db import conversation_repo
from app.db import database as db
from app.db.models import Base, Ticket
from app.graph.build import build_graph
from app.graph.runtime import Runtime
from app.graph.adapters import make_tool_registry
from app.schemas.chat import ChatRequest
from app.core.intent import Intent, Prediction


def classification(route):
    """返回意图分类结果"""
    labels = {"business": Intent.ORDER, "knowledge": Intent.PRODUCT, "chat": Intent.CHAT}
    return Prediction(intent=labels[route], confidence=0.95), route


@asynccontextmanager
async def database(monkeypatch):
    """创建内存数据库并初始化表结构"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(db, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield await conversation_repo.create_conversation("u1")
    finally:
        await engine.dispose()


def call(call_id):
    """构造工具调用记录"""
    return {"name": "create_ticket", "id": call_id,
            "args": {"ticket_type": "退款", "description": call_id}}


def services(replies=None, intent="business"):
    """构造测试用的服务Mock对象"""
    return SimpleNamespace(
        classify=AsyncMock(return_value=classification(intent)),
        retrieve_detailed=AsyncMock(return_value={
            "candidates": [],
            "evidence": [],
        }),
        check_sufficient=AsyncMock(return_value={"useful": True}),
        rerank_policy=AsyncMock(return_value=[]),
        expand_policy=AsyncMock(return_value=[]),
        answer=AsyncMock(return_value={
            "answer": "有据回答",
            "refused": False,
            "citations": [],
            "reason": None,
        }),
        agent=AsyncMock(side_effect=replies),
        tools={"create_ticket": AsyncMock(return_value={"preview": True})}, max_steps=3,
        registry=make_tool_registry(),
    )


def runtime(s):
    """构造运行时对象"""
    return Runtime(build_graph(s, InMemorySaver()))


async def chat(r, cid, text="建单"):
    """执行一次对话流"""
    return [frame async for frame in stream_graph_chat(
        ChatRequest(user_id="u1", conversation_id=cid, message=text), cid, r)]


async def ticket_count():
    """只查询 database() 替换后的一次性数据库。"""
    async with db.SessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(Ticket))


def events(frames):
    """解析 SSE 数据帧，结束标记不属于 JSON 事件。"""
    return [json.loads(line.removeprefix("data: "))
            for frame in frames for line in frame.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"]
