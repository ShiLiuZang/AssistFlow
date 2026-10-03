"""
进程内实时推送（人工坐席与顾客页面）

频道：
- "staff"：所有在线坐席，推送队列变化和顾客新消息
- "conversation:<id>"：该会话的顾客页面，推送坐席回复和接待状态

只在单实例内有效；多实例部署（阶段 4）需要换成 Redis Pub/Sub。
订阅者处理不过来（队列满）时直接断开，客户端重连后重新拉取一次即可。

长连接会让 uvicorn 退出时一直“等待连接关闭”，所以 install_shutdown_hook 在收到退出信号时
主动结束所有事件流。
"""

import asyncio
import json
import logging
import signal
import threading
from collections import defaultdict
from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

STAFF = "staff"
HEARTBEAT_SECONDS = 15.0
QUEUE_SIZE = 200
_CLOSED = object()


def conversation_channel(conversation_id: int) -> str:
    return f"conversation:{conversation_id}"


class Hub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self.closing = False

    def subscriber_count(self, channel: str) -> int:
        return len(self._subscribers.get(channel, ()))

    def publish(self, channel: str, event: dict) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("实时推送队列已满，断开订阅 channel=%s", channel)
                self._drop(channel, queue)
                self._close(queue)

    def _drop(self, channel: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(channel)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(channel, None)

    @staticmethod
    def _close(queue: asyncio.Queue) -> None:
        # 队列已满时腾出一个位置放结束标记
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        queue.put_nowait(_CLOSED)

    def close_all(self) -> None:
        """结束所有事件流（进程退出时）；之后新建的流立即结束。"""
        self.closing = True
        for channel, queues in list(self._subscribers.items()):
            for queue in list(queues):
                self._drop(channel, queue)
                self._close(queue)

    def close_all_threadsafe(self) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self.close_all)
        else:
            self.closing = True

    async def stream(self, channel: str, *, heartbeat: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
        """以 SSE 帧输出频道事件；空闲时输出注释行作为心跳，防止代理断开连接。"""
        if self.closing:
            return
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers[channel].add(queue)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if event is _CLOSED:
                    return
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        finally:
            self._drop(channel, queue)


hub = Hub()


def install_shutdown_hook() -> None:
    """进程收到 SIGINT / SIGTERM 时先结束事件流，再交给原来的处理函数（uvicorn 的退出流程）。

    uvicorn 在导入应用之前就装好了信号处理函数，所以这里在应用启动时包一层，而不是改 uvicorn 的类。
    只能在主线程安装；重复调用不会重复包装。
    """
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous = signal.getsignal(sig)
        if getattr(previous, "_closes_streams", False):
            continue

        def handler(signum, frame, previous=previous):
            hub.close_all_threadsafe()
            if callable(previous):
                previous(signum, frame)
            elif previous != signal.SIG_IGN:
                signal.signal(signum, signal.SIG_DFL)
                signal.raise_signal(signum)

        handler._closes_streams = True
        signal.signal(sig, handler)
