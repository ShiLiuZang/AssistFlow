"""
会话互斥：同一会话的图执行、工单确认、消息落库串行进行

调用方只使用 conversation_lock(user_id, conversation_id)，具体实现由后端决定：
默认 LocalLocks 只在单实例内生效；多实例部署（路线图阶段 4）时在启动时用 use_backend()
换成共享实现（例如 Redis 锁），调用方不用改。
"""
import asyncio
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol
from weakref import WeakValueDictionary


class LockBackend(Protocol):
    def lock(self, user_id: str, conversation_id: str) -> AbstractAsyncContextManager[None]:
        """同一会话互斥；同一任务内重入不能死锁。"""


class _Lock:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.owner = None


class LocalLocks:
    """进程内实现：同一任务可重入，空闲锁可回收。"""

    def __init__(self) -> None:
        self._locks = WeakValueDictionary()

    @asynccontextmanager
    async def lock(self, user_id: str, conversation_id: str):
        entry = self._locks.setdefault((user_id, conversation_id), _Lock())
        task = asyncio.current_task()
        if entry.owner is task:
            yield
            return
        async with entry.lock:
            entry.owner = task
            try:
                yield
            finally:
                entry.owner = None


_backend: LockBackend = LocalLocks()


def use_backend(backend: LockBackend) -> None:
    """替换会话锁实现（启动时调用）。"""
    global _backend
    _backend = backend


def conversation_lock(user_id: str, conversation_id: str | int) -> AbstractAsyncContextManager[None]:
    return _backend.lock(str(user_id), str(conversation_id))
