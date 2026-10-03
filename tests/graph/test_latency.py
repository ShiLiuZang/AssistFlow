"""回复时延：预取（检索、回答）、政策检索并行、意图规则、精排连接复用。"""
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import settings
from app.core import intent, rerank, retrieval
from app.core.intent import Intent
from app.graph import adapters, prefetch
from tests.graph.conftest import ANSWER, GOOD_HIT, make_services, runtime_for

WAIT = 1.0  # 等对方开始的上限；串行执行时会超时


class TestPrefetch:
    async def test_take_matching_key(self):
        prefetch.start("s", "x", "k", asyncio.sleep(0, result=42))
        assert await prefetch.take("s", "x", "k") == (True, 42)
        assert await prefetch.take("s", "x", "k") == (False, None)

    async def test_mismatch_cancels_and_recomputes(self):
        started = asyncio.Event()

        async def slow():
            started.set()
            await asyncio.sleep(10)

        prefetch.start("s", "x", "k1", slow())
        await started.wait()
        task = prefetch._tasks[("s", "x")][1]
        assert await prefetch.take("s", "x", "k2") == (False, None)
        await asyncio.sleep(0)
        assert task.cancelled()

    async def test_error_propagates(self):
        async def boom():
            raise RuntimeError("boom")

        prefetch.start("s", "x", "k", boom())
        with pytest.raises(RuntimeError):
            await prefetch.take("s", "x", "k")

    async def test_discard_scope(self):
        prefetch.start("s1", "a", "k", asyncio.sleep(10))
        prefetch.start("s1", "b", "k", asyncio.sleep(10))
        prefetch.start("s2", "a", "k", asyncio.sleep(10))
        prefetch.discard("s1")
        assert prefetch.pending("s1") == [] and prefetch.pending("s2") == ["a"]
        prefetch.discard("s2")

    def test_key_is_order_insensitive_for_dicts(self):
        assert prefetch.make_key({"a": 1, "b": 2}) == prefetch.make_key({"b": 2, "a": 1})


class TestSpeculativeAnswer:
    async def test_answer_runs_during_check(self, repo):
        answer_started = asyncio.Event()
        calls = []

        async def answer(query, evidence, *, order, summary_text):
            calls.append(query)
            answer_started.set()
            return {"answer": ANSWER, "refused": False, "citations": [{**evidence[0], "n": 1}], "reason": None}

        async def check(question, evidence):
            await asyncio.wait_for(answer_started.wait(), WAIT)  # 回答必须已经开始
            return {"useful": True}

        services = make_services(answer=answer, check_sufficient=check, speculative_answer=True)
        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")
        assert result["answer"] == ANSWER and calls == ["退货期限是多久"]
        assert prefetch.pending("c1") == []

    async def test_cancelled_when_check_rejects(self, repo):
        cancelled = asyncio.Event()

        async def answer(query, evidence, *, order, summary_text):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def check(question, evidence):
            await asyncio.sleep(0)
            return {"useful": False}

        services = make_services(answer=answer, check_sufficient=check, speculative_answer=True)
        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")
        assert "fallback" in result["trace"] and "answer" not in result["trace"]
        await asyncio.wait_for(cancelled.wait(), WAIT)

    async def test_same_result_with_and_without(self, repo):
        plain = await runtime_for(make_services()).run_turn("退货期限是多久", "u1", "c1")
        fast = await runtime_for(make_services(speculative_answer=True, speculative_retrieve=True)).run_turn(
            "退货期限是多久", "u1", "c1")
        assert (fast["answer"], fast["citations"], fast["trace"]) == (plain["answer"], plain["citations"], plain["trace"])

    async def test_policy_branch_uses_prefetch(self, repo):
        order = {"order_id": "ORD-1", "user_id": "u1", "product_name": "耳机"}
        seen = []
        answer_started = asyncio.Event()

        async def answer(query, evidence, *, order, summary_text):
            seen.append(order)
            answer_started.set()
            return {"answer": ANSWER, "refused": False, "citations": [{**evidence[0], "n": 1}], "reason": None}

        async def check(question, evidence):
            await asyncio.wait_for(answer_started.wait(), WAIT)
            return {"useful": True}

        services = make_services(route="refund", answer=answer, check_sufficient=check, speculative_answer=True,
                                 get_order=AsyncMock(return_value=order))
        result = await runtime_for(services).run_turn("ORD-1 能退吗", "u1", "c1")
        assert result["answer"] == ANSWER and seen == [order]


class TestSpeculativeRetrieve:
    def services(self, route, retrieve_calls, started):
        async def retrieve_detailed(query):
            retrieve_calls.append(query)
            started.set()
            await asyncio.sleep(0.01)
            return {"candidates": [GOOD_HIT], "evidence": [GOOD_HIT]}

        services = make_services(route=route, retrieve_detailed=retrieve_detailed, speculative_retrieve=True)
        classify = services.classify

        async def slow_classify(query, **kwargs):
            await asyncio.wait_for(started.wait(), WAIT)  # 检索必须已经开始
            return await classify(query, **kwargs)

        services.classify = slow_classify
        return services

    async def test_knowledge_uses_prefetched_retrieval(self, repo):
        calls, started = [], asyncio.Event()
        result = await runtime_for(self.services("knowledge", calls, started)).run_turn("退货期限是多久", "u1", "c1")
        assert result["answer"] == ANSWER and calls == ["退货期限是多久"]

    async def test_other_routes_cancel(self, repo):
        calls, started = [], asyncio.Event()
        result = await runtime_for(self.services("chat", calls, started)).run_turn("你们几点下班", "u1", "c1")
        assert "retrieve" not in result["trace"] and prefetch.pending("c1") == []


class TestPolicyParallel:
    async def test_search_overlaps_expand_and_each_other(self):
        first_started = asyncio.Event()
        running, peak = [0], [0]

        async def expand(query):
            await asyncio.wait_for(first_started.wait(), WAIT)  # 原问题的检索已经开始
            return ["改写一", "改写二"]

        async def search(query):
            first_started.set()
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.02)
            running[0] -= 1
            hit = {**GOOD_HIT, "id": query, "question": query}
            return {"candidates": [hit], "evidence": [hit]}

        async def rerank_all(query, hits, top_k):
            return [{**hit, "rerank_score": 0.9} for hit in hits]

        queries, result = await retrieval.retrieve_policy_detailed("能退吗", None, expand, search, rerank_all)
        assert queries == ["能退吗", "改写一", "改写二"]
        assert sorted(hit["id"] for hit in result["candidates"]) == sorted(["能退吗", "改写一", "改写二"])
        assert peak[0] >= 2

    async def test_error_cancels_others(self):
        cancelled = []

        async def expand(query):
            return ["慢", "坏"]

        async def search(query):
            if query == "坏":
                raise ValueError("检索失败")
            try:
                await asyncio.sleep(0 if query == "能退吗" else 10)
            except asyncio.CancelledError:
                cancelled.append(query)
                raise
            return {"candidates": [], "evidence": []}

        with pytest.raises(ValueError, match="检索失败"):
            await retrieval.retrieve_policy_detailed("能退吗", None, expand, search, AsyncMock())
        assert cancelled == ["慢"]

    async def test_expand_failure_cancels_first_search(self):
        cancelled = asyncio.Event()

        async def expand(query):
            await asyncio.sleep(0)  # 让原问题的检索先开始
            raise RuntimeError("expand down")

        async def search(query):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        with pytest.raises(RuntimeError):
            await retrieval.retrieve_policy_detailed("能退吗", None, expand, search, AsyncMock())
        await asyncio.wait_for(cancelled.wait(), WAIT)


class TestIntentRules:
    @pytest.mark.parametrize("text", ["在吗", "你好", "您好在吗？", "亲", "hello", "有人吗~", " 在 吗 "])
    def test_greetings(self, text):
        assert intent.quick_intent(text).intent == Intent.CHAT

    @pytest.mark.parametrize("text", ["人工", "转人工", "人工客服", "我要人工！", "帮我转人工", "找真人客服"])
    def test_human(self, text):
        assert intent.quick_intent(text).intent == Intent.HUMAN

    @pytest.mark.parametrize("text", ["不要人工", "人工审核要多久", "在吗 我的快递呢", "你好，退货运费谁出",
                                      "客服", "", "人工客服什么时候上班"])
    def test_needs_model(self, text):
        assert intent.quick_intent(text) is None

    async def test_classify_detail_skips_model(self, monkeypatch):
        monkeypatch.setattr(adapters, "get_chat_model", lambda: pytest.fail("不该调模型"))
        prediction, route = await adapters.classify_detail("转人工")
        assert (prediction.intent, route) == (Intent.HUMAN, "human")
        assert (await adapters.classify_detail("在吗"))[1] == "chat"

    async def test_rules_can_be_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "intent_rules", False)
        called = []

        class Model:
            def with_structured_output(self, *a, **k):
                return self

            async def ainvoke(self, messages):
                called.append(messages)
                raise RuntimeError("no model")

        monkeypatch.setattr(adapters, "get_chat_model", lambda: Model())
        prediction, route = await adapters.classify_detail("在吗")
        assert called and route == "clarify"


class TestRerankClient:
    async def test_reuses_connection_pool(self, monkeypatch):
        created = []
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            created.append(1)
            return original(*args, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": 1})),
                            **kwargs)

        monkeypatch.setattr(rerank, "_CLIENT", None)
        monkeypatch.setattr(rerank.httpx, "AsyncClient", factory)
        assert await rerank.post_with_retry("http://x/rerank", {}) == {"ok": 1}
        assert await rerank.post_with_retry("http://x/rerank", {}) == {"ok": 1}
        assert len(created) == 1
        await rerank.close_client()
        assert rerank._CLIENT is None


def test_production_services_enable_prefetch():
    services = adapters.make_services()
    assert services.speculative_retrieve is settings.speculative_retrieve is True
    assert services.speculative_answer is settings.speculative_answer is True
