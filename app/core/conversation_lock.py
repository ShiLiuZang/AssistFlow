"""本地单实例的会话互斥；同一任务可重入，空闲锁可回收。"""
import asyncio
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary


class _Lock:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.owner = None


_locks = WeakValueDictionary()


@asynccontextmanager
async def conversation_lock(user_id: str, conversation_id: str | int):
    key = (str(user_id), str(conversation_id))
    entry = _locks.setdefault(key, _Lock())
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
