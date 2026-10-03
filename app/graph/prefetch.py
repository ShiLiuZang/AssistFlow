"""
一轮对话内的预取

图的节点是串行的，但有些后续步骤在前一步还没出结果时就已经能开始：
- 意图识别（模型调用）期间，先开始知识检索（向量化、召回、精排都不调模型）
- 证据充分性检查（模型调用）期间，先开始生成回答

前一步的结果决定要不要用预取的结果：意图不是知识咨询、证据被拒，就取消预取。
预取结果只有在输入完全一致时才会被使用（take 比对 key），否则丢弃并重新计算，
所以开关预取不会改变回答，只会改变耗时。

任务按会话保存在进程内存里（同一会话的轮次由会话锁串行），
Runtime 在每轮结束时调用 discard 取消没用上的任务。
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Hashable

logger = logging.getLogger(__name__)

_tasks: dict[tuple[str, str], tuple[Hashable, asyncio.Task]] = {}


def make_key(*parts) -> str:
    """把输入序列化成可比较的 key（证据、订单是字典列表）。"""
    return json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)


def _silence(task: asyncio.Task) -> None:
    # 没被取走的任务出错时不打印 "Task exception was never retrieved"
    if not task.cancelled():
        task.exception()


def start(scope: str, name: str, key: Hashable, awaitable: Awaitable) -> None:
    cancel(scope, name)
    task = asyncio.ensure_future(awaitable)
    task.add_done_callback(_silence)
    _tasks[(scope, name)] = (key, task)


def cancel(scope: str, name: str) -> None:
    entry = _tasks.pop((scope, name), None)
    if entry is not None and not entry[1].done():
        entry[1].cancel()


async def take(scope: str, name: str, key: Hashable) -> tuple[bool, object]:
    """取出预取结果：(True, 结果)；没有预取或输入不一致时 (False, None)。预取出错时抛出同样的异常。"""
    entry = _tasks.pop((scope, name), None)
    if entry is None:
        return False, None
    expected, task = entry
    if expected != key:
        if not task.done():
            task.cancel()
        logger.debug("预取输入不一致，重新计算 name=%s", name)
        return False, None
    return True, await task


def discard(scope: str) -> None:
    for scope_name in [k for k in _tasks if k[0] == scope]:
        cancel(*scope_name)


def pending(scope: str) -> list[str]:
    return [name for (s, name) in _tasks if s == scope]
