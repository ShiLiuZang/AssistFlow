"""会话锁、限流、实时推送的后端可以在启动时整体替换，调用方不用改。"""
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException

from app.core import conversation_lock as lock_module, ratelimit, realtime
from app.core.conversation_lock import LocalLocks, conversation_lock


class TestConversationLock:
    async def test_custom_backend(self, monkeypatch):
        seen = []

        class Recording:
            @asynccontextmanager
            async def lock(self, user_id, conversation_id):
                seen.append((user_id, conversation_id))
                yield

        monkeypatch.setattr(lock_module, "_backend", lock_module._backend)
        lock_module.use_backend(Recording())
        async with conversation_lock("u1", 7):
            pass
        assert seen == [("u1", "7")]

    async def test_local_locks_reentrant(self):
        locks = LocalLocks()
        async with locks.lock("u1", "7"):
            async with locks.lock("u1", "7"):  # 同一任务重入不死锁
                pass


class TestRateLimiter:
    async def test_custom_backend(self, monkeypatch):
        class DenyAll:
            window = 30

            def hit(self, key, limit):
                return False

            def reset(self):
                pass

        monkeypatch.setattr(ratelimit, "limiter", ratelimit.limiter)
        ratelimit.use_limiter(DenyAll())
        with pytest.raises(HTTPException) as error:
            await ratelimit.limit_customer_chat("u1")
        assert error.value.status_code == 429 and error.value.headers["Retry-After"] == "30"


class TestHub:
    def test_custom_backend(self, monkeypatch):
        from app.core import handoff

        published = []

        class Recording(realtime.Hub):
            def publish(self, channel, event):
                published.append(channel)

        monkeypatch.setattr(realtime, "hub", realtime.hub)
        realtime.use_hub(Recording())
        handoff._publish_message(handoff._event(7, handoff.EVENT_ACCEPTED))
        assert "conversation:7" in published
