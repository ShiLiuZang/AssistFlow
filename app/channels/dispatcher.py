"""
渠道消息调度

一条买家消息的处理过程：
1. 入站：登记（按平台消息 ID 去重）后立即返回，渠道桥不用等 AI 回答
2. 合并：买家常把一句话拆成几条连发，同一买家静默 channel_merge_seconds 后把这几条合成一轮
3. 处理：同一买家的消息串行处理；会话在人工接待中时直接进坐席队列；
   有待确认操作（建单、选订单）时把买家的文字回复当作确认；否则走一轮图
4. 安抚：超过 channel_hold_seconds 还没答完，先发一句“正在查询”，避免平台判定超时未回复
5. 出站：转成纯文本、去掉站外链接和联系方式、按长度拆分后经渠道桥发出
6. 人工：坐席在工作台的回复和接入、结束提示，经实时推送回调发回平台

图的执行复用网页聊天的流程（stream_graph_chat / stream_ticket_decision / stream_order_selection），
这里只解析它们输出的 SSE 帧，保证两个入口的行为一致。

调度状态在进程内存里，只支持单实例（与阶段 2 的实时推送相同，阶段 4 再换）。
进程重启时，最近还没处理的入站消息会补处理。
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from uuid import uuid4

from app.api.actions import _interrupt, stream_order_selection, stream_ticket_decision
from app.api.graph_chat import _thread_config, stream_graph_chat
from app.channels import store
from app.channels.pinduoduo import CHANNEL, USER_PREFIX, PddInbound, event_text, sanitize
from app.channels.sender import send_with_retry
from app.channels.text import (
    order_prompt, parse_confirmation, parse_order_choice, split_message, ticket_prompt,
)
from app.core import handoff
from app.core.conversation_lock import conversation_lock
from app.db import repository
from app.schemas.actions import ResumeTicketRequest, SelectOrderRequest
from app.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)

HOLD_TEXT = "正在为您查询，请稍等～"
BUSY_TEXT = "抱歉，当前咨询较多，请稍后再发一次，或回复「人工」转人工客服。"
MEDIA_TEXT = "暂时看不了图片和视频，麻烦用文字描述一下您的问题～"
MEDIA_NOTE = "[买家发送了图片或视频，请在拼多多商家后台查看]"
RECOVER_MINUTES = 10
TEXT_KINDS = {"text", "goods", "order"}


def parse_frames(frames: list[str]) -> list[dict]:
    """把聊天接口输出的 SSE 帧还原成事件字典（跳过 [DONE] 和心跳）。"""
    events = []
    for frame in frames:
        name = data = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except ValueError:
            continue
        if name and "event" not in payload:
            payload["event"] = name
        events.append(payload)
    return events


def render(events: list[dict]) -> list[tuple[str, str]]:
    """一轮事件转成要发给买家的消息 [(类型, 文本)]。"""
    if any(e.get("event") == "done" and e.get("handoff") is True for e in events):
        return []  # 人工接待中，消息已进坐席队列（graph_chat 在 done 里带 handoff: true）
    answer = "".join(str(e["delta"]) for e in events if "delta" in e).strip()
    replies = [("answer", answer)] if answer else []
    interrupt = next((e for e in events if e.get("event") == "interrupt"), None)
    if interrupt is not None:
        if interrupt.get("kind") == "select_order":
            replies.append(("answer", order_prompt(interrupt.get("orders") or [])))
        else:
            replies.append(("answer", ticket_prompt(interrupt.get("preview") or {})))
    if not replies and any(e.get("event") == "error" for e in events):
        replies.append(("notice", BUSY_TEXT))
    return replies


class Dispatcher:
    def __init__(self, *, runtime_getter: Callable, sender, merge_seconds: float = 1.5,
                 merge_max_seconds: float = 6, hold_seconds: float = 8, idle_minutes: int = 1440,
                 max_chars: int = 500):
        self.runtime_getter = runtime_getter
        self.sender = sender
        self.merge_seconds = merge_seconds
        self.merge_max_seconds = merge_max_seconds
        self.hold_seconds = hold_seconds
        self.idle_minutes = idle_minutes
        self.max_chars = max_chars
        self._buffers: dict[int, list[dict]] = {}
        self._workers: dict[int, asyncio.Task] = {}
        self._forwarding: dict[int, asyncio.Task] = {}
        self._background: set[asyncio.Task] = set()

    # ==================== 入站 ====================

    async def receive(self, payload: PddInbound) -> dict:
        accepted, duplicates = [], []
        for event in payload.events:
            session = await store.get_or_create_session(CHANNEL, payload.shop_id, event.buyer_id, USER_PREFIX)
            if event.order_sn:
                await store.attest_order(CHANNEL, event.order_sn, session["user_id"], event.goods_name)
            text = event_text(event)
            row_id = await store.record_inbound(CHANNEL, session["session_id"], event.msg_id, event.type,
                                                text if text is not None else f"[{event.type}]")
            if row_id is None:
                duplicates.append(event.msg_id)
                continue
            accepted.append(event.msg_id)
            self.submit(session["session_id"], {"id": row_id, "text": text})
        return {"accepted": accepted, "duplicates": duplicates}

    def submit(self, session_id: int, item: dict) -> None:
        self._buffers.setdefault(session_id, []).append(item)
        if session_id not in self._workers:
            task = asyncio.create_task(self._drain(session_id))
            self._workers[session_id] = task

    async def _drain(self, session_id: int) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self._buffers.get(session_id):
                started = loop.time()
                while True:  # 买家还在连发就继续等，最多 merge_max_seconds
                    count = len(self._buffers[session_id])
                    await asyncio.sleep(self.merge_seconds)
                    if len(self._buffers[session_id]) == count or loop.time() - started >= self.merge_max_seconds:
                        break
                batch = self._buffers.pop(session_id)
                await self._process(session_id, batch)
        finally:
            self._workers.pop(session_id, None)

    async def _process(self, session_id: int, batch: list[dict]) -> None:
        ids = [item["id"] for item in batch]
        conversation_id = None
        try:
            session = await store.current_conversation(session_id, self.idle_minutes)
            conversation_id = session["conversation_id"]
            texts = [item["text"] for item in batch if item["text"]]
            if texts:
                replies = await self._answer(session, "\n".join(texts)[:2000])
            elif await handoff.customer_message(conversation_id, session["user_id"], MEDIA_NOTE) is not None:
                replies = []
            else:
                replies = [("notice", MEDIA_TEXT)]
            await self._deliver(session, replies)
            await store.finish_inbound(ids, "done", conversation_id)
        except Exception as error:
            logger.exception("渠道消息处理失败 session_id=%s", session_id)
            try:
                await store.finish_inbound(ids, "failed", conversation_id, type(error).__name__)
                session = await store.get_session(session_id)
                if session is not None:
                    await self._deliver({**session, "conversation_id": conversation_id}, [("notice", BUSY_TEXT)])
            except Exception:
                logger.exception("渠道消息失败处理出错 session_id=%s", session_id)

    # ==================== 回答 ====================

    async def _answer(self, session: dict, message: str) -> list[tuple[str, str]]:
        runtime = self.runtime_getter()
        if runtime is None:
            return [("notice", BUSY_TEXT)]
        user_id, conversation_id = session["user_id"], session["conversation_id"]

        # 人工接待中：消息进坐席队列，不回复
        if await handoff.customer_message(conversation_id, user_id, message) is not None:
            return []

        pending = await self._pending(runtime, user_id, conversation_id)
        if pending is not None and pending.get("kind") == "select_order":
            orders = pending.get("orders") or []
            choice = parse_order_choice(message, orders)
            if choice is None:
                return [("answer", "没看懂您选的是哪一笔订单。\n" + order_prompt(orders))]
            frames = stream_order_selection(SelectOrderRequest(
                conversation_id=conversation_id, user_id=user_id, request_id=pending["request_id"],
                order_id=choice or None, cancelled=choice is False), runtime)
        elif pending is not None:
            decision = parse_confirmation(message)
            if decision is None:
                return [("answer", "请先处理这张工单，再继续其他问题。\n" + ticket_prompt(pending.get("preview") or {}))]
            tool_call = await self._ticket_call(conversation_id, pending["tool_call_id"])
            if tool_call is None:
                return [("notice", BUSY_TEXT)]
            frames = stream_ticket_decision(ResumeTicketRequest(
                conversation_id=conversation_id, user_id=user_id, confirmed=decision,
                tool_call_id=pending["tool_call_id"]), tool_call, runtime)
        else:
            request = ChatRequest(message=message, conversation_id=conversation_id, user_id=user_id)
            frames = stream_graph_chat(request, conversation_id, runtime)
        return render(await self._collect(session, frames))

    async def _pending(self, runtime, user_id: str, conversation_id: int) -> dict | None:
        async with conversation_lock(user_id, conversation_id):
            snapshot = await runtime.graph.aget_state(_thread_config(user_id, conversation_id))
            return _interrupt(snapshot)

    @staticmethod
    async def _ticket_call(conversation_id: int, call_id: str) -> dict | None:
        records = await repository.list_messages(conversation_id)
        return next((call for record in reversed(records) for call in record.tool_calls or []
                     if call.get("id") == call_id and call.get("name") == "create_ticket"), None)

    async def _collect(self, session: dict, frames: AsyncIterator[str]) -> list[dict]:
        async def collect() -> list[str]:
            return [frame async for frame in frames]

        task = asyncio.create_task(collect())
        if self.hold_seconds > 0:
            done, _ = await asyncio.wait({task}, timeout=self.hold_seconds)
            if not done:
                await self._deliver(session, [("hold", HOLD_TEXT)])
        return parse_frames(await task)

    # ==================== 出站 ====================

    async def _deliver(self, session: dict, replies: list[tuple[str, str]]) -> None:
        for kind, text in replies:
            for part in split_message(sanitize(text), self.max_chars):
                result = await send_with_retry(self.sender, shop_id=session["shop_id"],
                                               buyer_id=session["buyer_id"], text=part,
                                               idempotency_key=uuid4().hex)
                try:
                    await store.record_outbound(CHANNEL, session["session_id"], kind, part, result.status,
                                                attempts=result.attempts, error=result.error,
                                                conversation_id=session.get("conversation_id"))
                except Exception:
                    logger.exception("渠道发送记录写入失败")
                if result.status == "failed":
                    return

    def on_publish(self, channel: str, event: dict) -> None:
        """实时推送回调：坐席回复和接入、结束提示发回平台（网页会话查不到渠道映射，直接跳过）。"""
        if not channel.startswith("conversation:") or event.get("type") != "message":
            return
        message = event.get("message") or {}
        content = str(message.get("content") or "")
        if message.get("role") == "staff":
            kind = "staff"
        elif message.get("role") == "system" and content in (handoff.EVENT_ACCEPTED, handoff.EVENT_CLOSED):
            kind = "system"
        else:
            return
        try:
            conversation_id = int(channel.split(":", 1)[1])
            asyncio.get_running_loop()
        except (ValueError, RuntimeError):
            return
        previous = self._forwarding.get(conversation_id)
        task = asyncio.create_task(self._forward(conversation_id, kind, content, previous))
        self._forwarding[conversation_id] = task
        self._background.add(task)

        def done(finished: asyncio.Task) -> None:
            self._background.discard(finished)
            if self._forwarding.get(conversation_id) is finished:
                self._forwarding.pop(conversation_id, None)

        task.add_done_callback(done)

    async def _forward(self, conversation_id: int, kind: str, content: str, previous: asyncio.Task | None) -> None:
        if previous is not None:  # 同一会话的坐席消息按顺序发
            await asyncio.wait({previous})
        try:
            session = await store.session_for_conversation(conversation_id)
            if session is not None:
                await self._deliver(session, [(kind, content)])
        except Exception:
            logger.exception("坐席回复发回渠道失败 conversation_id=%s", conversation_id)

    # ==================== 生命周期 ====================

    async def recover(self) -> int:
        """补处理重启前还没处理的入站消息；太久以前的标为过期。"""
        await store.expire_pending(CHANNEL, RECOVER_MINUTES)
        rows = await store.pending_inbound(CHANNEL, RECOVER_MINUTES)
        for row in rows:
            self.submit(row["session_id"], {"id": row["id"],
                                            "text": row["content"] if row["kind"] in TEXT_KINDS else None})
        return len(rows)

    async def close(self, timeout: float = 5) -> None:
        """等进行中的处理收尾；超时就取消，没处理完的入站消息下次启动补处理。"""
        tasks = [*self._workers.values(), *self._background]
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        self._buffers.clear()
