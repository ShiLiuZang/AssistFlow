"""渠道调度：去重、合并连发、安抚、人工接待、文字确认、坐席回复回发、补处理、会话轮换。"""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.channels import dispatcher as dispatcher_module, store
from app.channels.dispatcher import BUSY_TEXT, HOLD_TEXT, MEDIA_TEXT, Dispatcher, render
from app.channels.pinduoduo import PddInbound
from app.channels.sender import SendError
from app.core import handoff
from app.core.realtime import Hub
from app.graph import turns
from app.db.models import ChannelMessage, ChannelSession, Handoff

ORDER = "231003-123456789012345"


class FakeSender:
    dry_run = False

    def __init__(self, fail=None):
        self.sent = []
        self.fail = fail

    async def send(self, *, shop_id, buyer_id, text, idempotency_key):
        if self.fail:
            raise self.fail
        self.sent.append((shop_id, buyer_id, text))

    @property
    def texts(self):
        return [text for _, _, text in self.sent]


class FakeGraph:
    """替代 turns.chat_turn：记录收到的消息，按脚本返回事件。"""

    def __init__(self, answer="您好，有什么可以帮您？", delay=0.0, events=None):
        self.calls = []
        self.answer, self.delay, self.events = answer, delay, events

    async def __call__(self, request, conversation_id, runtime):
        self.calls.append((request.user_id, conversation_id, request.message))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.events or [{"delta": self.answer}, {"event": "done"}]


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph()
    monkeypatch.setattr(dispatcher_module, "chat_turn", fake)
    return fake


@pytest.fixture
def pending(monkeypatch):
    state = {"value": None}

    async def fake_pending(runtime, user_id, conversation_id):
        return state["value"]

    monkeypatch.setattr(dispatcher_module, "pending_interrupt", fake_pending)
    return state


@pytest.fixture
def sender():
    return FakeSender()


@pytest.fixture
def make(db, sender, graph, pending):
    def factory(**overrides):
        options = dict(runtime_getter=lambda: object(), sender=sender, merge_seconds=0.01,
                       merge_max_seconds=0.2, hold_seconds=0, idle_minutes=60, max_chars=500)
        options.update(overrides)
        return Dispatcher(**options)
    return factory


async def settle(dispatcher):
    for _ in range(50):
        tasks = [*dispatcher._workers.values(), *dispatcher._background]
        if not tasks:
            return
        await asyncio.gather(*tasks)


def inbound(*events, shop="shop1"):
    return PddInbound.model_validate({"shop_id": shop, "events": [
        {"buyer_id": "buyer1", **event} for event in events]})


async def rows(factory, direction):
    async with factory() as session:
        result = await session.scalars(select(ChannelMessage).where(ChannelMessage.direction == direction)
                                       .order_by(ChannelMessage.id))
        return list(result)


class TestFrames:
    def test_render(self):
        assert render([{"delta": "你好"}, {"delta": "呀"}, {"event": "done"}]) == [("answer", "你好呀")]
        routed = [{"event": "conversation"}, {"event": "handoff", "handoff": {"status": "queued"}, "message": {}},
                  {"event": "done", "message_id": None, "handoff": True}]
        assert render(routed) == []
        # 本轮刚转入排队：done 不带 handoff，正常发出 AI 的回答
        assert render([{"delta": "已为您转接人工客服"}, {"event": "handoff", "handoff": {"status": "queued"}},
                       {"event": "done"}]) == [("answer", "已为您转接人工客服")]
        assert render([{"event": "error", "message": "x"}]) == [("notice", BUSY_TEXT)]
        ticket = render([{"event": "interrupt", "kind": "confirm_ticket", "tool_call_id": "c1",
                          "preview": {"ticket_type": "退款", "description": "破损"}}])
        assert "「退款」" in ticket[0][1]
        orders = render([{"event": "interrupt", "kind": "select_order", "request_id": "r",
                          "orders": [{"order_id": ORDER, "product_name": "杯子"}]}])
        assert ORDER in orders[0][1]


class TestInboundFlow:
    async def test_answers_and_records(self, make, db, sender, graph):
        dispatcher = make()
        result = await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        assert result == {"accepted": ["m1"], "duplicates": []}
        assert sender.sent == [("shop1", "buyer1", "您好，有什么可以帮您？")]
        user_id, conversation_id, message = graph.calls[0]
        assert user_id.startswith("pdd-") and "buyer1" not in user_id and message == "在吗"
        [row] = await rows(db, "in")
        assert row.status == "done" and row.conversation_id == conversation_id
        [out] = await rows(db, "out")
        assert out.status == "sent" and out.kind == "answer"

    async def test_duplicates_ignored(self, make, sender, graph):
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        result = await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        assert result == {"accepted": [], "duplicates": ["m1"]}
        assert len(graph.calls) == 1 and len(sender.sent) == 1

    async def test_merges_burst(self, make, graph):
        dispatcher = make(merge_seconds=0.05)
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "你好"}))
        await asyncio.sleep(0.01)
        await dispatcher.receive(inbound({"msg_id": "m2", "text": "我的杯子"}, {"msg_id": "m3", "text": "漏水了"}))
        await settle(dispatcher)
        assert [call[2] for call in graph.calls] == ["你好\n我的杯子\n漏水了"]

    async def test_buyers_are_separate(self, make, graph):
        dispatcher = make()
        await dispatcher.receive(PddInbound.model_validate({"shop_id": "s", "events": [
            {"msg_id": "m1", "buyer_id": "a", "text": "A"}, {"msg_id": "m2", "buyer_id": "b", "text": "B"}]}))
        await settle(dispatcher)
        assert sorted(call[2] for call in graph.calls) == ["A", "B"]
        assert len({call[0] for call in graph.calls}) == 2

    async def test_hold_message_when_slow(self, make, sender, graph):
        graph.delay = 0.2
        dispatcher = make(hold_seconds=0.05)
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "我的快递到哪了"}))
        await settle(dispatcher)
        assert sender.texts == [HOLD_TEXT, "您好，有什么可以帮您？"]

    async def test_no_hold_when_fast(self, make, sender):
        dispatcher = make(hold_seconds=0.5)
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        assert sender.texts == ["您好，有什么可以帮您？"]

    async def test_long_answer_split_and_sanitized(self, make, sender, graph):
        graph.answer = "**退货规则**[1]：" + "请保持包装完好。" * 30 + "详见 https://x.example"
        dispatcher = make(max_chars=100)
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "怎么退货"}))
        await settle(dispatcher)
        assert len(sender.texts) > 1 and all(len(t) <= 100 for t in sender.texts)
        assert sender.texts[0].startswith("退货规则：") and not any("http" in t for t in sender.texts)

    async def test_media_only(self, make, sender, graph):
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m1", "type": "image"}))
        await settle(dispatcher)
        assert sender.texts == [MEDIA_TEXT] and graph.calls == []

    async def test_order_card_attested(self, make, db, graph):
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m1", "type": "order", "order_sn": ORDER, "goods_name": "保温杯",
                                          "text": "这单什么时候发货"}))
        await settle(dispatcher)
        user_id, _, message = graph.calls[0]
        assert message == f"[订单 {ORDER}] 保温杯\n这单什么时候发货"
        assert await store.order_owner("pinduoduo", ORDER) == {"user_id": user_id, "goods_name": "保温杯"}

    async def test_graph_error_sends_busy_text(self, make, sender, graph):
        graph.events = [{"event": "error", "message": "图执行失败"}]
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        assert sender.texts == [BUSY_TEXT]

    async def test_crash_marks_failed_and_apologizes(self, make, db, sender, monkeypatch):
        async def boom(self, session, message):
            raise RuntimeError("boom")
        monkeypatch.setattr(Dispatcher, "_answer", boom)
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        [row] = await rows(db, "in")
        assert row.status == "failed" and row.error == "RuntimeError"
        assert sender.texts == [BUSY_TEXT]

    async def test_runtime_not_ready(self, make, sender, graph):
        dispatcher = make(runtime_getter=lambda: None)
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        assert sender.texts == [BUSY_TEXT] and graph.calls == []

    async def test_send_failure_recorded(self, make, db, monkeypatch):
        monkeypatch.setattr(dispatcher_module, "send_with_retry", _no_retry)
        dispatcher = make(sender=FakeSender(fail=SendError("http 400", retryable=False)))
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await settle(dispatcher)
        [out] = await rows(db, "out")
        assert out.status == "failed" and out.error == "http 400"
        [row] = await rows(db, "in")
        assert row.status == "done"


async def _no_retry(sender, **kwargs):
    from app.channels.sender import send_with_retry
    return await send_with_retry(sender, retries=0, **kwargs)


class TestPendingActions:
    async def _conversation(self, dispatcher):
        await dispatcher.receive(inbound({"msg_id": "m0", "text": "你好"}))
        await settle(dispatcher)

    async def test_ticket_confirmation_by_text(self, make, sender, graph, pending, monkeypatch):
        dispatcher = make()
        await self._conversation(dispatcher)
        pending["value"] = {"kind": "confirm_ticket", "tool_call_id": "c1",
                            "preview": {"ticket_type": "退款", "description": "破损"}}
        decisions = []

        async def fake_list(conversation_id):
            class Row:
                tool_calls = [{"id": "c1", "name": "create_ticket", "args": {}}]
            return [Row()]

        async def fake_decision(request, tool_call, runtime):
            decisions.append((request.confirmed, request.tool_call_id, tool_call["id"], request.user_id))
            return [{"delta": "工单已创建，工单号：T1"}]

        monkeypatch.setattr(turns.conversation_repo, "list_messages", fake_list)
        monkeypatch.setattr(dispatcher_module, "ticket_decision_turn", fake_decision)

        await dispatcher.receive(inbound({"msg_id": "m1", "text": "运费谁出"}))
        await settle(dispatcher)
        assert "请先处理这张工单" in sender.texts[-1] and decisions == []

        await dispatcher.receive(inbound({"msg_id": "m2", "text": "确认"}))
        await settle(dispatcher)
        assert decisions[0][:3] == (True, "c1", "c1") and decisions[0][3].startswith("pdd-")
        assert sender.texts[-1] == "工单已创建，工单号：T1"
        assert len(graph.calls) == 1  # 确认不走新一轮图

    async def test_order_selection_by_text(self, make, sender, pending, monkeypatch):
        dispatcher = make()
        await self._conversation(dispatcher)
        pending["value"] = {"kind": "select_order", "request_id": "r1",
                            "orders": [{"order_id": ORDER, "product_name": "杯子"}]}
        selections = []

        async def fake_select(request, runtime):
            selections.append((request.request_id, request.order_id, request.cancelled))
            return [{"delta": "这笔订单已发货"}]

        monkeypatch.setattr(dispatcher_module, "order_selection_turn", fake_select)
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "哪个都不是"}))
        await settle(dispatcher)
        assert "没看懂" in sender.texts[-1] and selections == []
        await dispatcher.receive(inbound({"msg_id": "m2", "text": "1"}))
        await settle(dispatcher)
        assert selections == [("r1", ORDER, False)] and sender.texts[-1] == "这笔订单已发货"
        await dispatcher.receive(inbound({"msg_id": "m3", "text": "取消"}))
        await settle(dispatcher)
        assert selections[-1] == ("r1", None, True)


class TestHandoff:
    async def _session(self, db):
        async with db() as session:
            return (await session.scalars(select(ChannelSession))).one()

    async def test_messages_go_to_staff_during_handoff(self, make, db, sender, graph, monkeypatch):
        monkeypatch.setattr(handoff, "hub", Hub())
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m0", "text": "你好"}))
        await settle(dispatcher)
        row = await self._session(db)
        await handoff.request(row.conversation_id, row.user_id, "human", card={})
        sent_before = len(sender.sent)
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "快点处理"}, {"msg_id": "m2", "type": "image"}))
        await settle(dispatcher)
        assert len(graph.calls) == 1 and len(sender.sent) == sent_before
        detail = await handoff.detail(row.conversation_id)
        assert detail["channel"] == "pinduoduo"
        assert [m["content"] for m in detail["messages"] if m["role"] == "customer"][-1] == "快点处理"

    @pytest.mark.parametrize("runtime_ready", [True, False])
    async def test_human_request_bypasses_graph(self, make, db, sender, graph, monkeypatch, runtime_ready):
        monkeypatch.setattr(handoff, "hub", Hub())
        dispatcher = make(runtime_getter=(lambda: object()) if runtime_ready else (lambda: None))
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "转人工"}))
        await settle(dispatcher)
        assert graph.calls == []
        assert sender.texts == ["好的，已为您转接人工客服，您是下一位，客服接入后会在这里回复您。"]
        row = await self._session(db)
        detail = await handoff.detail(row.conversation_id)
        assert detail["status"] == "queued" and detail["handoff"]["reason"] == "human"

    async def test_human_request_while_ticket_pending(self, make, db, sender, graph, pending, monkeypatch):
        monkeypatch.setattr(handoff, "hub", Hub())
        pending["value"] = {"kind": "confirm_ticket", "tool_call_id": "c1", "preview": {}}
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "人工"}))
        await settle(dispatcher)
        row = await self._session(db)
        assert (await handoff.detail(row.conversation_id))["status"] == "queued"
        assert "转接人工客服" in sender.texts[-1]

    async def test_staff_replies_forwarded_in_order(self, make, db, sender, monkeypatch):
        hub = Hub()
        monkeypatch.setattr(handoff, "hub", hub)
        dispatcher = make()
        hub.add_listener(dispatcher.on_publish)
        await dispatcher.receive(inbound({"msg_id": "m0", "text": "你好"}))
        await settle(dispatcher)
        row = await self._session(db)
        await handoff.request(row.conversation_id, row.user_id, "human", card={})
        await handoff.accept(row.conversation_id, "alice")
        await handoff.post(row.conversation_id, "alice", "您好，我是客服小A")
        await handoff.post(row.conversation_id, "alice", "内部备注", kind="note")
        await handoff.post(row.conversation_id, "alice", "已为您登记退款")
        await handoff.close(row.conversation_id, "alice")
        await settle(dispatcher)
        assert sender.texts[1:] == [handoff.EVENT_ACCEPTED, "您好，我是客服小A", "已为您登记退款", handoff.EVENT_CLOSED]
        kinds = [r.kind for r in await rows(db, "out")]
        assert kinds[1:] == ["system", "staff", "staff", "system"]

    async def test_web_conversations_not_forwarded(self, make, sender):
        dispatcher = make()
        dispatcher.on_publish("conversation:999", {"type": "message", "message": {"role": "staff", "content": "hi"}})
        dispatcher.on_publish("staff", {"type": "message", "message": {"role": "staff", "content": "hi"}})
        await settle(dispatcher)
        assert sender.sent == []


class TestLifecycle:
    async def test_recover_pending(self, make, db, graph):
        session = await store.get_or_create_session("pinduoduo", "shop1", "buyer1", "pdd-")
        fresh = await store.record_inbound("pinduoduo", session["session_id"], "m1", "text", "还在吗")
        old = await store.record_inbound("pinduoduo", session["session_id"], "m0", "text", "很久以前")
        async with db() as s:
            await s.execute(update(ChannelMessage).where(ChannelMessage.id == old).values(
                created_at=store._now() - timedelta(hours=1)))
            await s.commit()
        dispatcher = make()
        assert await dispatcher.recover() == 1
        await settle(dispatcher)
        assert [call[2] for call in graph.calls] == ["还在吗"]
        statuses = {r.id: r.status for r in await rows(db, "in")}
        assert statuses == {fresh: "done", old: "expired"}

    async def test_conversation_rolls_over_after_idle(self, db):
        session = await store.get_or_create_session("pinduoduo", "shop1", "buyer1", "pdd-")
        first = await store.current_conversation(session["session_id"], 60)
        again = await store.current_conversation(session["session_id"], 60)
        assert first["new"] and not again["new"] and again["conversation_id"] == first["conversation_id"]
        await _age(db, session["session_id"])
        later = await store.current_conversation(session["session_id"], 60)
        assert later["new"] and later["conversation_id"] != first["conversation_id"]
        assert later["user_id"] == first["user_id"]

    async def test_no_rollover_during_handoff(self, db):
        session = await store.get_or_create_session("pinduoduo", "shop1", "buyer1", "pdd-")
        first = await store.current_conversation(session["session_id"], 60)
        async with db() as s:
            s.add(Handoff(conversation_id=first["conversation_id"], user_id=first["user_id"], status="queued",
                          reason="human"))
            await s.commit()
        await _age(db, session["session_id"])
        later = await store.current_conversation(session["session_id"], 60)
        assert not later["new"] and later["conversation_id"] == first["conversation_id"]

    async def test_close_waits_for_work(self, make, sender, graph):
        graph.delay = 0.05
        dispatcher = make()
        await dispatcher.receive(inbound({"msg_id": "m1", "text": "在吗"}))
        await dispatcher.close(timeout=2)
        assert sender.texts == ["您好，有什么可以帮您？"]


async def _age(db, session_id):
    async with db() as s:
        await s.execute(update(ChannelSession).where(ChannelSession.id == session_id).values(
            last_inbound_at=store._now() - timedelta(hours=2)))
        await s.commit()
