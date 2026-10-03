import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import database
from app.db.models import Base


@pytest.fixture
async def db(monkeypatch, tmp_path):
    # 用文件库而不是 :memory:：调度会并发处理多个买家，内存库只有一条共享连接
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'channels.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    yield factory
    await engine.dispose()
