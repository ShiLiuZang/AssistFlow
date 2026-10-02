"""
进程内滑动窗口限流

只在单实例内生效；多实例部署时换成 Redis 实现（路线图阶段 4），调用方只依赖 hit()。
"""

import time
from collections import deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.core.auth import Staff, current_customer, current_staff


class RateLimiter:
    def __init__(self, window_seconds: float = 60, clock: Callable[[], float] = time.monotonic):
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int) -> bool:
        """记录一次访问；窗口内已达上限时返回 False（本次不计入）。"""
        now = self.clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        self._prune(now)
        return True

    def _prune(self, now: float) -> None:
        # 键数过多时清掉已过期的键，避免长期运行内存增长
        if len(self._hits) < 10_000:
            return
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


def _deny(message: str) -> HTTPException:
    return HTTPException(429, message, headers={"Retry-After": str(int(limiter.window))})


async def limit_customer_chat(user_id: str = Depends(current_customer)) -> str:
    """顾客发消息限流，同时返回顾客 ID，接口可以直接拿来用。"""
    if not limiter.hit(f"chat:{user_id}", settings.rate_chat_per_minute):
        raise _deny("发送太频繁，请稍后再试")
    return user_id


async def limit_staff_model(staff: Staff = Depends(current_staff)) -> Staff:
    """员工调用模型的试用接口限流。"""
    if not limiter.hit(f"staff-model:{staff.username}", settings.rate_staff_model_per_minute):
        raise _deny("调用太频繁，请稍后再试")
    return staff


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def limit_login(request: Request) -> None:
    if not limiter.hit(f"login:{client_ip(request)}", settings.rate_login_per_minute):
        raise _deny("登录尝试过于频繁，请稍后再试")
