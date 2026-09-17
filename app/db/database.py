"""异步 MySQL 连接和数据库会话工厂。"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


engine = create_async_engine(settings.handwritten_database_url, pool_pre_ping=True)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """为一次业务操作提供独立数据库会话。"""
    async with SessionLocal() as session:
        yield session
