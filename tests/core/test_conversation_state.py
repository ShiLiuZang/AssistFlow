"""对话状态相关的纯逻辑：指代消解、消息窗口、滚动摘要、会话锁。"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import coref, memory, summarizer
from app.core.conversation_lock import conversation_lock
from app.core.memory import Message
from app.core.summarizer import Summary
from tests.helpers import FakeStructuredModel, patch_model


def human(content):
    return SimpleNamespace(type="human", content=content)


class TestEntities:
    def test_extracts_orders_and_models_uppercased_and_deduped(self):
        assert coref.entities("ord-12 和 MH-a1，还有 ORD-12") == ["ORD-12", "MH-A1"]

    @pytest.mark.parametrize("text", ["XORD-12", "ORD-12A", "MH-A1-B", "ORD-ABC"])
    def test_requires_token_boundaries(self, text):
        assert coref.entities(text) == []


class TestResolve:
    def test_no_reference_unchanged(self):
        assert coref.resolve("退货政策", []) == coref.Resolution("退货政策", "退货政策")

    def test_entity_in_current_query_wins(self):
        result = coref.resolve("ORD-1 这个订单能退吗", [human("ORD-2")])
        assert result.resolved == "ORD-1 ORD-1能退吗"
        assert result.needs_clarification is False

    def test_uses_single_historical_entity(self):
        result = coref.resolve("那个订单能退吗", [human("查一下 ORD-7")])
        assert result == coref.Resolution("那个订单能退吗", "ORD-7能退吗")

    def test_ignores_non_human_history(self):
        history = [SimpleNamespace(type="ai", content="ORD-9"), human("ORD-7")]
        assert coref.resolve("它到哪了", history).resolved == "ORD-7到哪了"

    def test_selected_order_counts_as_candidate(self):
        assert coref.resolve("这单能退吗", [], "ORD-3").resolved == "ORD-3能退吗"

    def test_same_entity_from_history_and_selection(self):
        assert coref.resolve("这单能退吗", [human("ORD-3")], "ORD-3").needs_clarification is False

    @pytest.mark.parametrize(
        "history,selected",
        [([], None), ([human("ORD-1"), human("ORD-2")], None), ([human("ORD-1")], "ORD-2")],
    )
    def test_ambiguous_needs_clarification(self, history, selected):
        result = coref.resolve("那个订单能退吗", history, selected)
        assert result == coref.Resolution("那个订单能退吗", "那个订单能退吗", True)


def msg(i, role, content="x", calls=(), call_id=None):
    return Message(i, role, content, tuple(calls), call_id)


TOOL_TURN = [
    msg(1, "human", "查订单"),
    msg(2, "ai", calls=["c1", "c2"]),
    msg(3, "tool", call_id="c1"),
    msg(4, "tool", call_id="c2"),
    msg(5, "ai", "已发货"),
    msg(6, "human", "谢谢"),
    msg(7, "ai", "不客气"),
]


class TestTurns:
    def test_groups_by_human(self):
        groups = memory.turns(TOOL_TURN)
        assert [[m.id for m in g] for g in groups] == [[1, 2, 3, 4, 5], [6, 7]]

    def test_group_turns_is_lenient(self):
        loose = [msg(1, "ai"), msg(1, "human"), msg(0, "human")]
        assert [len(g) for g in memory.group_turns(loose)] == [1, 1, 1]

    @pytest.mark.parametrize(
        "messages,error",
        [
            ([msg(2, "human"), msg(1, "ai")], "increase"),
            ([msg(1, "ai")], "begin with human"),
            ([msg(1, "human"), msg(2, "ai", calls=["c"]), msg(3, "human")], "unfinished"),
            ([msg(1, "human"), msg(2, "tool", call_id="c")], "orphan"),
            ([msg(1, "human"), msg(2, "ai", calls=["c"]), msg(3, "ai")], "missing"),
            ([msg(1, "human"), msg(2, "ai", calls=["c", "c"])], "duplicate call"),
            ([msg(1, "human"), msg(2, "system")], "human/ai/tool"),
            ([msg(1, "human"), msg(2, "ai", calls=["c"])], "finish tool"),
        ],
    )
    def test_rejects_invalid_history(self, messages, error):
        with pytest.raises(ValueError, match=error):
            memory.turns(messages)


def test_estimate_counts_json_plus_overhead():
    message = msg(1, "human", "你好")
    assert memory.estimate([message]) > len("你好") + 8
    assert memory.estimate([message, message]) == 2 * memory.estimate([message])


class TestBuildWindow:
    def test_keeps_whole_turns_within_budget(self):
        window = memory.build_window(TOOL_TURN, budget=10_000, keep=3)
        assert [m.id for m in window] == [1, 2, 3, 4, 5, 6, 7]

    def test_drops_older_turns_when_over_budget(self):
        count = lambda messages: len(messages)  # noqa: E731
        window = memory.build_window(TOOL_TURN, budget=3, keep=3, count=count)
        assert [m.id for m in window] == [6, 7]

    def test_keep_limits_turns(self):
        assert [m.id for m in memory.build_window(TOOL_TURN, 10_000, keep=1)] == [6, 7]

    def test_reserve_counts_against_budget(self):
        count = lambda messages: len(messages)  # noqa: E731
        with pytest.raises(ValueError, match="current turn"):
            memory.build_window(TOOL_TURN, budget=3, reserve=2, count=count)

    @pytest.mark.parametrize("budget,reserve,keep", [(10, 10, 1), (10, -1, 1), (10, 0, 0)])
    def test_rejects_invalid_arguments(self, budget, reserve, keep):
        with pytest.raises(ValueError, match="invalid"):
            memory.build_window(TOOL_TURN, budget, reserve, keep)


class TestComputeBoundary:
    def test_returns_last_id_before_kept_turns(self):
        three_turns = TOOL_TURN + [msg(8, "human"), msg(9, "ai")]
        assert summarizer.compute_boundary(three_turns, keep=2) == 5
        assert summarizer.compute_boundary(three_turns, keep=1) == 7

    def test_zero_when_not_enough_turns(self):
        assert summarizer.compute_boundary(TOOL_TURN, keep=2) == 0

    def test_rejects_keep_below_one(self):
        with pytest.raises(ValueError):
            summarizer.compute_boundary(TOOL_TURN, keep=0)


THREE_TURNS = [
    msg(1, "human", "a"), msg(2, "ai", "b"),
    msg(3, "human", "c"), msg(4, "ai", "d"),
    msg(5, "human", "e"), msg(6, "ai", "f"),
]


class TestSummarizeDelta:
    async def test_summarizes_messages_before_boundary(self):
        summarize = AsyncMock(return_value=" 新摘要 ")

        result = await summarizer.summarize_delta(Summary("旧", 0), THREE_TURNS, summarize, keep=2)

        assert result == Summary("新摘要", 2)
        old_text, delta = summarize.await_args.args
        assert old_text == "旧"
        assert [m.id for m in delta] == [1, 2]

    async def test_only_new_messages_since_cursor(self):
        summarize = AsyncMock(return_value="x")
        await summarizer.summarize_delta(Summary("旧", 2), THREE_TURNS, summarize, keep=1)
        assert [m.id for m in summarize.await_args.args[1]] == [3, 4]

    async def test_below_threshold_keeps_old(self):
        summarize = AsyncMock()
        old = Summary("旧", 0)
        assert await summarizer.summarize_delta(old, THREE_TURNS, summarize, keep=2, threshold=3) is old
        summarize.assert_not_awaited()

    @pytest.mark.parametrize("text", ["", "  ", None])
    async def test_rejects_empty_summary(self, text):
        with pytest.raises(ValueError, match="empty"):
            await summarizer.summarize_delta(Summary(), THREE_TURNS, AsyncMock(return_value=text))


async def test_summary_store_serializes_per_key():
    store = summarizer.SummaryStore()
    summarize = AsyncMock(return_value="摘要")

    first = await store.update("k", THREE_TURNS, summarize)
    second = await store.update("k", THREE_TURNS, summarize)

    assert first == second == Summary("摘要", 2)
    assert summarize.await_count == 1
    assert store.records["k"] == first


class TestAssemble:
    def test_prefix_and_window(self):
        prefix, window = summarizer.assemble("系统", Summary("摘要", 2), THREE_TURNS, budget=10_000)
        assert prefix[0] == {"role": "system", "content": "系统"}
        assert '"untrusted_conversation_summary"' in prefix[1]["content"]
        assert [m.id for m in window] == [3, 4, 5, 6]

    def test_no_summary_no_user_prefix(self):
        prefix, window = summarizer.assemble("系统", Summary(), THREE_TURNS, budget=10_000)
        assert len(prefix) == 1
        assert len(window) == 6


class TestSummarizeDialog:
    async def test_payload_and_result(self, monkeypatch):
        model = patch_model(
            monkeypatch, summarizer,
            FakeStructuredModel(summarizer.SummaryOutput(summary=" 用户要退货 ")),
        )
        delta = (msg(1, "human", "我要退货"), msg(2, "ai", "", calls=["c1"]), msg(3, "tool", "{}", call_id="c1"))

        assert await summarizer.summarize_dialog("旧摘要", delta) == "用户要退货"

        import json
        payload = json.loads(model.calls[0][1][1])
        assert payload["previous_summary"] == "旧摘要"
        assert payload["new_messages"] == [
            {"role": "用户", "content": "我要退货"},
            {"role": "助手", "content": "[助手发起工具调用，ID：c1]"},
            {"role": "工具返回", "content": "{}"},
        ]

    @pytest.mark.parametrize(
        "model",
        [FakeStructuredModel(parsing_error=ValueError("x")), FakeStructuredModel(parsed=None)],
    )
    async def test_errors(self, monkeypatch, model):
        patch_model(monkeypatch, summarizer, model)
        with pytest.raises(ValueError):
            await summarizer.summarize_dialog("", (msg(1, "human", "a"),))


class TestPersistedSummaryScheduling:
    @pytest.fixture(autouse=True)
    def clean_running(self):
        summarizer._running.clear()
        yield
        summarizer._running.clear()

    async def test_schedule_dedupes_running_task(self, monkeypatch):
        gate = asyncio.Event()
        calls = []

        async def update(user_id, conversation_id, summarize, *, keep, threshold):
            calls.append((user_id, conversation_id, keep, threshold))
            await gate.wait()

        monkeypatch.setattr(summarizer, "update_persisted_summary", update)

        assert summarizer.schedule_persisted_summary("u1", 1, None) is True
        assert summarizer.schedule_persisted_summary("u1", 1, None) is False
        assert summarizer.schedule_persisted_summary("u1", 2, None) is True

        gate.set()
        await asyncio.gather(*summarizer._running.values())
        await asyncio.sleep(0)
        assert summarizer._running == {}
        assert calls == [("u1", 1, 2, 30), ("u1", 2, 2, 30)]

    async def test_failed_task_is_logged_and_removed(self, monkeypatch, caplog):
        async def update(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(summarizer, "update_persisted_summary", update)

        summarizer.schedule_persisted_summary("u1", 1, None)
        await asyncio.gather(*summarizer._running.values(), return_exceptions=True)
        await asyncio.sleep(0)

        assert summarizer._running == {}
        assert "summary failed" in caplog.text

    async def test_close_cancels_running_tasks(self, monkeypatch):
        async def update(*args, **kwargs):
            await asyncio.sleep(10)

        monkeypatch.setattr(summarizer, "update_persisted_summary", update)
        summarizer.schedule_persisted_summary("u1", 1, None)
        task = summarizer._running[("u1", 1)]

        await summarizer.close_persisted_summaries()

        assert task.cancelled()

    async def test_update_retries_conflicts(self, monkeypatch):
        from app.core import persistent_summary

        attempts = []

        class Store:
            async def update(self, key, summarize, keep, threshold):
                attempts.append(key)
                if len(attempts) < 3:
                    raise persistent_summary.SummaryConflict()
                return Summary("ok", 1)

        monkeypatch.setattr(persistent_summary, "PersistentSummaryStore", Store)

        assert await summarizer.update_persisted_summary("u1", 1, None) == Summary("ok", 1)
        assert attempts == [("u1", 1)] * 3

    async def test_update_gives_up_after_three_conflicts(self, monkeypatch):
        from app.core import persistent_summary

        class Store:
            async def update(self, *args, **kwargs):
                raise persistent_summary.SummaryConflict()

        monkeypatch.setattr(persistent_summary, "PersistentSummaryStore", Store)
        with pytest.raises(persistent_summary.SummaryConflict):
            await summarizer.update_persisted_summary("u1", 1, None)


class TestConversationLock:
    async def test_serializes_same_conversation(self):
        order = []

        async def worker(name):
            async with conversation_lock("u1", 1):
                order.append(f"{name}-in")
                await asyncio.sleep(0.01)
                order.append(f"{name}-out")

        await asyncio.gather(worker("a"), worker("b"))
        assert order == ["a-in", "a-out", "b-in", "b-out"]

    async def test_reentrant_in_same_task(self):
        async with conversation_lock("u1", "1"):
            async with conversation_lock("u1", 1):
                entered = True
        assert entered

    async def test_different_conversations_run_concurrently(self):
        inside = asyncio.Event()

        async def holder():
            async with conversation_lock("u1", 1):
                inside.set()
                await asyncio.sleep(0.05)

        task = asyncio.create_task(holder())
        await inside.wait()
        async with asyncio.timeout(0.02):
            async with conversation_lock("u1", 2):
                pass
        await task
