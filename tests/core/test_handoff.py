"""人工坐席闭环：转人工、接入、回复、转交、结束、回流与工单（内存 SQLite，不连 MySQL）。"""
import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import handoff, realtime, tickets
from app.core.handoff import HandoffError, HandoffForbidden
from app.db import database
from app.db.models import Base, Conversation, Handoff, LowConfidenceQuestion, Message, StaffUser


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    yield factory
    await engine.dispose()


@pytest.fixture
def published(monkeypatch):
    events = []
    monkeypatch.setattr(realtime.hub, "publish", lambda channel, event: events.append((channel, event)))
    return events


async def add_conversation(factory, *messages, user_id="u1"):
    async with factory() as session:
        conversation = Conversation(user_id=user_id)
        session.add(conversation)
        await session.flush()
        for role, content in messages:
            session.add(Message(conversation_id=conversation.id, role=role, content=content))
        await session.commit()
        return conversation.id


async def add_staff(factory, username, role="agent", active=True):
    async with factory() as session:
        session.add(StaffUser(username=username, password_hash="x", role=role, active=active))
        await session.commit()


async def roles(factory, conversation_id):
    async with factory() as session:
        rows = await session.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id))
        return [(row.role, row.content) for row in rows]


class TestCard:
    def test_mood_levels(self):
        assert handoff.detect_mood(["我要投诉你们，太离谱了"])["level"] == "angry"
        assert handoff.detect_mood(["怎么还没发货？？"])["level"] == "upset"
        assert handoff.detect_mood(["请问可以开发票吗"]) == {"level": "calm", "label": "平稳", "hits": [], "method": "keyword"}

    def test_build_card(self):
        card = handoff.build_card(
            reason="complaint", dialog=[("customer", "耳机坏了"), ("bot", "抱歉"), ("customer", "我要投诉")],
            summary_text="顾客反馈耳机质量问题", intent="投诉",
            evidence=[{"section_path": "售后/质量问题", "answer": "质量问题 15 天内可换货"}, "bad"],
            order={"order_id": "ORD-1", "product_name": "耳机", "user_id": "u1", "status": "已签收"},
        )
        assert card["reason_label"] == "顾客投诉"
        assert card["last_question"] == "我要投诉"
        assert card["evidence"] == [{"title": "售后/质量问题", "text": "质量问题 15 天内可换货"}]
        assert card["order"] == {"order_id": "ORD-1", "product_name": "耳机", "status": "已签收"}
        assert card["mood"]["level"] == "angry"

    def test_card_from_state_skips_tool_messages(self):
        from langchain_core.messages import AIMessage, HumanMessage
        state = {"messages": [HumanMessage(content="查订单"), AIMessage(content="", tool_calls=[{"id": "1", "name": "q", "args": {}}]),
                              AIMessage(content="已查到"), HumanMessage(content="转人工")],
                 "query": "转人工", "summary_text": "", "intent_detail": "转人工"}
        card = handoff.card_from_state(state, "human")
        assert [item["role"] for item in card["recent"]] == ["customer", "bot", "customer"]

    def test_pair_dialog(self):
        rows = [Message(role="user", content="能开发票吗"), Message(role="staff", content="您好"),
                Message(role="handoff_user", content="公司抬头"), Message(role="staff", content="可以开具增值税普通发票，请在订单页申请")]
        assert handoff.pair_dialog(rows) == [("能开发票吗\n公司抬头", "可以开具增值税普通发票，请在订单页申请")]


class TestCustomerSide:
    async def test_request_is_idempotent_and_queued(self, db, published):
        cid = await add_conversation(db, ("user", "我要投诉"))
        first = await handoff.request(cid, "u1", "customer_request")
        again = await handoff.request(cid, "u1", "customer_request")

        assert first["status"] == "queued" and first["position"] == 1 and first["created"] is True
        assert again["id"] == first["id"] and again["created"] is False
        assert "card" not in first  # 卡片只给坐席看
        assert [r for r, _ in await roles(db, cid)] == ["user", "handoff_event"]
        assert {channel for channel, _ in published} == {"staff", f"conversation:{cid}"}

    async def test_queue_position(self, db, published):
        a = await add_conversation(db, ("user", "a"))
        b = await add_conversation(db, ("user", "b"), user_id="u2")
        await handoff.request(a, "u1", "human")
        assert (await handoff.request(b, "u2", "human"))["position"] == 2

    async def test_other_customer_cannot_request(self, db, published):
        cid = await add_conversation(db, ("user", "a"))
        with pytest.raises(LookupError):
            await handoff.request(cid, "intruder", "customer_request")

    async def test_staff_takeover_reason_not_allowed_for_customer(self, db):
        cid = await add_conversation(db)
        with pytest.raises(ValueError):
            await handoff.request(cid, "u1", "staff_takeover")

    async def test_customer_message_only_routed_when_open(self, db, published):
        cid = await add_conversation(db, ("user", "a"))
        assert await handoff.customer_message(cid, "u1", "在吗") is None
        await handoff.request(cid, "u1", "human")
        routed = await handoff.customer_message(cid, "u1", "在吗")
        assert routed["message"]["role"] == "customer" and routed["handoff"]["status"] == "queued"
        assert (await roles(db, cid))[-1] == ("handoff_user", "在吗")

    async def test_cancel_only_while_queued(self, db, published):
        cid = await add_conversation(db, ("user", "a"))
        await handoff.request(cid, "u1", "human")
        assert (await handoff.cancel(cid, "u1"))["status"] == "cancelled"
        assert await handoff.customer_status(cid, "u1") is None

        await handoff.request(cid, "u1", "human")
        await handoff.accept(cid, "alice")
        with pytest.raises(HandoffError, match="已接入"):
            await handoff.cancel(cid, "u1")


class TestStaffSide:
    async def test_accept_reply_close_flow(self, db, published):
        await add_staff(db, "alice")
        cid = await add_conversation(db, ("user", "发票怎么开"), ("assistant", "抱歉，暂时没有找到"))
        await handoff.request(cid, "u1", "human")

        with pytest.raises(HandoffError, match="先接入"):
            await handoff.post(cid, "alice", "你好")
        accepted = await handoff.accept(cid, "alice")
        assert accepted["status"] == "active" and accepted["assignee"] == "alice"
        assert await handoff.accept(cid, "alice") == accepted  # 重复接入无副作用
        with pytest.raises(HandoffError, match="alice"):
            await handoff.accept(cid, "bob")

        with pytest.raises(HandoffForbidden):
            await handoff.post(cid, "bob", "我来回复")
        note = await handoff.post(cid, "bob", "这位顾客上周也问过", kind="note")
        reply = await handoff.post(cid, "alice", "可以在订单详情页申请电子发票，手机号13812345678的话会短信通知")
        assert note["role"] == "note" and reply["role"] == "staff" and reply["author"] == "alice"

        # 备注不推给顾客
        customer_events = [e for c, e in published if c == f"conversation:{cid}" and e["type"] == "message"]
        assert [e["message"]["role"] for e in customer_events] == ["system", "system", "staff"]

        closed = await handoff.close(cid, "alice")
        assert closed["status"] == "closed" and closed["harvested"] == 1
        async with db() as session:
            pool = list(await session.scalars(select(LowConfidenceQuestion)))
        assert len(pool) == 1 and pool[0].source == "human_handoff" and pool[0].question == "发票怎么开"
        assert "[手机号]" in pool[0].reason and handoff.harvested_answer({"source": pool[0].source, "reason": pool[0].reason})
        assert await handoff.harvest(closed["id"]) == 0  # 幂等

        detail = await handoff.detail(cid)
        assert detail["status"] == "ai"
        assert [m["role"] for m in detail["messages"]] == ["customer", "bot", "system", "system", "note", "staff", "system"]

    async def test_close_permissions(self, db, published):
        cid = await add_conversation(db, ("user", "a"))
        await handoff.request(cid, "u1", "human")
        await handoff.accept(cid, "alice")
        with pytest.raises(HandoffForbidden):
            await handoff.close(cid, "bob")
        assert (await handoff.close(cid, "boss", is_admin=True))["closed_by"] == "boss"
        with pytest.raises(HandoffError):
            await handoff.close(cid, "alice")

    async def test_takeover_ai_conversation(self, db, published):
        cid = await add_conversation(db, ("user", "猫砂盆尺寸"), ("assistant", "长 50 厘米"))
        taken = await handoff.accept(cid, "alice")
        assert taken["reason"] == "staff_takeover" and taken["status"] == "active"
        assert taken["card"]["recent"][-1] == {"role": "bot", "content": "长 50 厘米"}

    async def test_transfer(self, db, published):
        await add_staff(db, "alice")
        await add_staff(db, "bob")
        await add_staff(db, "rita", role="reviewer")
        await add_staff(db, "gone", active=False)
        cid = await add_conversation(db, ("user", "a"))
        await handoff.request(cid, "u1", "human")
        await handoff.accept(cid, "alice")

        for target in ("rita", "gone", "nobody"):
            with pytest.raises(HandoffError):
                await handoff.transfer(cid, "alice", target)
        with pytest.raises(HandoffForbidden):
            await handoff.transfer(cid, "bob", "bob")
        assert (await handoff.transfer(cid, "alice", "bob"))["assignee"] == "bob"
        assert (await roles(db, cid))[-1] == ("staff_note", "会话由 alice 转交给 bob")
        assert [u["username"] for u in await handoff.staff_users()] == ["alice", "bob"]

    async def test_lists_and_counts(self, db, published):
        queued = await add_conversation(db, ("user", "排队的"))
        mine = await add_conversation(db, ("user", "我的"), user_id="u2")
        ai = await add_conversation(db, ("user", "AI 的"), user_id="u3")
        await handoff.request(queued, "u1", "human")
        await handoff.accept(mine, "alice")

        assert [i["conversation_id"] for i in await handoff.list_for_staff("queued", "alice")] == [queued]
        assert [i["conversation_id"] for i in await handoff.list_for_staff("mine", "alice")] == [mine]
        assert [i["conversation_id"] for i in await handoff.list_for_staff("mine", "bob")] == []
        assert {i["conversation_id"] for i in await handoff.list_for_staff("active", "bob")} == {queued, mine}
        ai_items = await handoff.list_for_staff("ai", "alice")
        assert [i["conversation_id"] for i in ai_items] == [ai]
        assert ai_items[0]["last_message"]["content"] == "AI 的"
        assert await handoff.counts("alice") == {"queued": 1, "mine": 1, "active": 1}
        with pytest.raises(ValueError):
            await handoff.list_for_staff("bogus", "alice")


class TestTickets:
    async def test_create_and_transition(self, db):
        cid = await add_conversation(db)
        backend = tickets.LocalTicketBackend()
        created = await backend.create(conversation_id=cid, user_id="u1", ticket_type="补发", title="肩带缺件",
                                       description="顾客反馈肩带缺失", priority="优先", actor="alice", source="staff")
        no = created["ticket_no"]
        assert created["status"] == "待处理" and created["events"][0]["note"] == "坐席创建"

        with pytest.raises(tickets.TicketError, match="不能从"):
            await backend.transition(no, "已解决", "alice")
        working = await backend.transition(no, "处理中", "alice", "联系仓库")
        assert working["assignee"] == "alice"
        with pytest.raises(tickets.TicketError, match="已是"):
            await backend.transition(no, "处理中", "alice")
        noted = await backend.transition(no, "处理中", "bob", "仓库已回复")
        assert noted["events"][-1]["action"] == "note" and noted["assignee"] == "alice"
        await backend.transition(no, "已解决", "alice")
        await backend.transition(no, "已关闭", "alice")
        with pytest.raises(tickets.TicketError):
            await backend.transition(no, "处理中", "alice")

        detail = await backend.get(no)
        assert [e["to_status"] for e in detail["events"]] == ["待处理", "处理中", None, "已解决", "已关闭"]
        assert await backend.stats() == {"待处理": 0, "处理中": 0, "已解决": 0, "已关闭": 1}
        assert [t["ticket_no"] for t in await backend.list(q="肩带")] == [no]
        assert await backend.list(status="待处理") == []
        assert await backend.get("T0") is None

    async def test_create_requires_owned_conversation(self, db):
        cid = await add_conversation(db)
        with pytest.raises(LookupError):
            await tickets.LocalTicketBackend().create(conversation_id=cid, user_id="other", ticket_type="咨询",
                                                      title="t", description="d", actor="alice")


class TestHub:
    async def test_stream_delivers_and_heartbeats(self):
        hub = realtime.Hub()
        stream = hub.stream("staff", heartbeat=0.05)
        assert await anext(stream) == ": connected\n\n"
        assert await anext(stream) == ": ping\n\n"
        hub.publish("staff", {"type": "x", "text": "你好"})
        assert await anext(stream) == 'data: {"type": "x", "text": "你好"}\n\n'
        await stream.aclose()
        assert hub.subscriber_count("staff") == 0

    async def test_slow_subscriber_is_dropped(self, monkeypatch):
        monkeypatch.setattr(realtime, "QUEUE_SIZE", 2)
        hub = realtime.Hub()
        stream = hub.stream("c", heartbeat=5)
        await anext(stream)
        task = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0)
        for i in range(5):
            hub.publish("c", {"i": i})
        assert hub.subscriber_count("c") == 0
        await task
        with pytest.raises(StopAsyncIteration):
            while True:
                await anext(stream)


class TestShutdown:
    async def test_close_all_ends_streams(self):
        hub = realtime.Hub()
        stream = hub.stream("staff", heartbeat=5)
        await anext(stream)
        task = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0)
        hub.close_all_threadsafe()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(task, 1)
        assert [chunk async for chunk in hub.stream("staff")] == []  # 退出过程中新连接立即结束

    def test_signal_hook_closes_streams_then_delegates(self, monkeypatch):
        import signal
        calls = []
        saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        monkeypatch.setattr(realtime.hub, "close_all_threadsafe", lambda: calls.append("close"))
        try:
            signal.signal(signal.SIGTERM, lambda signum, frame: calls.append(("previous", signum)))
            realtime.install_shutdown_hook()
            installed = signal.getsignal(signal.SIGTERM)
            realtime.install_shutdown_hook()
            assert signal.getsignal(signal.SIGTERM) is installed  # 不重复包装
            installed(signal.SIGTERM, None)
            assert calls == ["close", ("previous", signal.SIGTERM)]
        finally:
            for sig, handler in saved.items():
                signal.signal(sig, handler)
