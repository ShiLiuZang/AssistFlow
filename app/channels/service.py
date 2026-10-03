"""渠道接入的启动与关闭（在 app.main 的 lifespan 里调用）。"""

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

from app.channels.dispatcher import Dispatcher
from app.channels.pinduoduo import PddOrderProvider
from app.channels.sender import BridgeSender, DryRunSender
from app.config import settings
from app.core.realtime import hub
from app.tools import orders

logger = logging.getLogger(__name__)

MIN_SECRET_LENGTH = 32
dispatcher: Dispatcher | None = None


class ChannelConfigError(RuntimeError):
    """渠道配置不满足要求（拒绝启动）。"""


def check_configuration() -> None:
    if settings.pdd_enabled and len(settings.pdd_bridge_secret.strip()) < MIN_SECRET_LENGTH:
        raise ChannelConfigError(f"已开启拼多多渠道，但 PDD_BRIDGE_SECRET 未配置或少于 {MIN_SECRET_LENGTH} 字符")


def make_sender():
    if settings.pdd_bridge_send_url.strip():
        return BridgeSender(settings.pdd_bridge_send_url.strip(), settings.pdd_bridge_secret.strip())
    logger.warning("拼多多渠道：未配置 PDD_BRIDGE_SEND_URL，回复只记录不发送（演练模式）")
    return DryRunSender()


@asynccontextmanager
async def running(runtime_getter: Callable):
    """开启拼多多渠道时：注册订单来源、坐席回复回调，补处理重启前的消息；退出时收尾。"""
    global dispatcher
    if not settings.pdd_enabled:
        yield None
        return
    check_configuration()
    provider = PddOrderProvider()
    dispatcher = Dispatcher(
        runtime_getter=runtime_getter, sender=make_sender(),
        merge_seconds=settings.channel_merge_seconds, merge_max_seconds=settings.channel_merge_max_seconds,
        hold_seconds=settings.channel_hold_seconds, idle_minutes=settings.channel_idle_minutes,
        max_chars=settings.pdd_max_message_chars,
    )
    orders.register_provider(provider)
    hub.add_listener(dispatcher.on_publish)
    try:
        try:
            recovered = await dispatcher.recover()
            if recovered:
                logger.info("拼多多渠道：补处理 %s 条重启前未处理的消息", recovered)
        except Exception:
            logger.exception("拼多多渠道：补处理未完成消息失败")
        yield dispatcher
    finally:
        hub.remove_listener(dispatcher.on_publish)
        orders.unregister_provider(provider)
        await dispatcher.close()
        dispatcher = None
