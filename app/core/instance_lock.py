"""
单实例保护

会话锁、限流、实时推送、渠道调度和预取都在进程内存里（阶段 4 才换成 Redis）。
同一台机器上起了多个进程（uvicorn --workers N、重复启动）时，这些状态各管各的：
同一会话会在两个进程里同时跑图，渠道消息会被重复补处理，坐席回复推不到另一个进程的顾客。

所以启动时对检查点文件旁边的锁文件加独占锁，拿不到就拒绝启动。
锁随进程退出自动释放（包括被杀掉），不会留下需要手动清理的状态。
跨机器的多副本这里拦不住，部署时只能起一个副本。
"""

import logging
import os
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # Windows 没有 fcntl，只告警不拦截
    fcntl = None


class InstanceLockError(RuntimeError):
    """已有另一个进程在运行（拒绝启动）。"""


@contextmanager
def single_instance(path: str | Path):
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        logger.warning("当前系统不支持文件锁，无法检查是否有多个进程同时运行；请确认只启动了一个进程")
        yield
        return
    handle = open(lock_path, "a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstanceLockError(
                f"已有另一个进程在运行（锁文件 {lock_path}）。当前版本只支持单进程：不要用 --workers 启动多个进程，"
                "也不要重复启动；确需多实例要等阶段 4（Redis）。"
            ) from None
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        yield
    finally:
        handle.close()  # 关闭文件即释放锁
