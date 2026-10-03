"""app.kb.retrieval：检索编排。Milvus、向量化、问题改写、重排均为替身。"""
from unittest.mock import AsyncMock

import pytest

from app.kb import retrieval
from app.kb import milvus_client
from tests.helpers import make_hit


class TestSplitRankedHits:
    def test_partitions_by_min_score(self):
        result = retrieval.split_ranked_hits(
            [make_hit(1, 0.2), make_hit(2, 0.9), make_hit(3, 0.3)], min_score=0.3,
        )
        assert [h["id"] for h in result["candidates"]] == [2, 3, 1]
        assert [h["id"] for h in result["evidence"]] == [2, 3]

    def test_evidence_independent_from_candidates(self):
        result = retrieval.split_ranked_hits([make_hit(1, 0.9)], min_score=0.3)
        result["evidence"][0]["answer"] = "changed"
        assert result["candidates"][0]["answer"] == "a1"

    def test_empty(self):
        assert retrieval.split_ranked_hits([], 0.5) == {"candidates": [], "evidence": []}

    @pytest.mark.parametrize("bad", [-1, 1.1, float("nan"), True, "0.3"])
    def test_rejects_invalid_min_score(self, bad):
        with pytest.raises(ValueError):
            retrieval.split_ranked_hits([], min_score=bad)


class TestSplitClauses:
    @pytest.mark.parametrize(
        "query,expected",
        [
            ("退货政策是什么，运费由谁承担？", ["退货政策是什么", "运费由谁承担"]),
            ("退货政策是什么;运费由谁承担。保修多长时间", ["退货政策是什么", "运费由谁承担", "保修多长时间"]),
        ],
    )
    def test_splits_on_punctuation(self, query, expected):
        assert retrieval.split_clauses(query) == expected

    @pytest.mark.parametrize("query", ["退货政策是什么，好？", "单句问题", "短，句"])
    def test_falls_back_to_original(self, query):
        assert retrieval.split_clauses(query) == [query]


class TestMergeRoundRobin:
    def test_interleaves_and_dedups(self):
        groups = [[make_hit(1), make_hit(2), make_hit(3)], [make_hit(2), make_hit(4)], []]
        assert [h["id"] for h in retrieval.merge_round_robin(groups)] == [1, 2, 4, 3]

    def test_empty(self):
        assert retrieval.merge_round_robin([]) == []
        assert retrieval.merge_round_robin([[], []]) == []


@pytest.fixture
def backend(monkeypatch):
    """替换 Milvus 与向量化；每次检索返回 3 条以调用序号编号的命中。"""
    calls = []

    async def acall(fn):
        return fn()

    def fake(kind):
        def search(client, *args, **kwargs):
            calls.append({"kind": kind, "client": client, "args": args, "kwargs": kwargs})
            n = len(calls)
            return [make_hit(n * 10 + i) for i in range(3)]
        return search

    ensured = []
    monkeypatch.setattr(milvus_client, "acall", acall)
    monkeypatch.setattr(milvus_client, "ensure_collection", lambda c, **k: ensured.append((c, k)))
    monkeypatch.setattr(milvus_client, "dense_search", fake("dense"))
    monkeypatch.setattr(milvus_client, "bm25_search", fake("bm25"))
    monkeypatch.setattr(milvus_client, "hybrid_search", fake("hybrid"))
    shared_client = object()
    monkeypatch.setattr(milvus_client, "get_client", lambda: shared_client)
    embed = AsyncMock(return_value=[0.0] * milvus_client.DIM)
    monkeypatch.setattr(retrieval.embeddings, "embed_query", embed)
    return {"calls": calls, "embed": embed, "ensured": ensured, "client": shared_client}


class TestSearchKnowledgeDetailed:
    async def test_rejects_unknown_strategy(self):
        with pytest.raises(ValueError, match="检索策略"):
            await retrieval.search_knowledge_detailed("q", strategy="magic")

    async def test_rejects_non_positive_top_k(self):
        with pytest.raises(ValueError, match="top_k"):
            await retrieval.search_knowledge_detailed("q", top_k=0)

    async def test_vector(self, backend):
        result = await retrieval.search_knowledge_detailed(
            "退货政策", strategy="vector", top_k=2, category="售后",
        )

        assert result == {"candidates": None, "evidence": [make_hit(10), make_hit(11)]}
        call = backend["calls"][0]
        assert call["kind"] == "dense"
        assert call["client"] is backend["client"]
        assert call["args"][1] == 2
        assert call["kwargs"] == {"collection": milvus_client.COLLECTION, "category": "售后"}
        backend["embed"].assert_awaited_once_with("退货政策")
        assert backend["ensured"] == [(backend["client"], {"collection": milvus_client.COLLECTION})]

    async def test_explicit_client_and_collection(self, backend):
        mine = object()
        await retrieval.search_knowledge_detailed("q", client=mine, collection="other")
        assert backend["calls"][0]["client"] is mine
        assert backend["calls"][0]["kwargs"]["collection"] == "other"

    async def test_bm25_skips_embedding(self, backend):
        await retrieval.search_knowledge_detailed("退货", strategy="bm25")
        assert backend["calls"][0]["kind"] == "bm25"
        assert backend["calls"][0]["args"][0] == "退货"
        backend["embed"].assert_not_awaited()

    async def test_hybrid_passes_recall(self, backend):
        await retrieval.search_knowledge_detailed("q", strategy="hybrid", top_k=3)
        call = backend["calls"][0]
        assert call["kind"] == "hybrid"
        assert call["args"][2] == 3
        assert call["kwargs"]["recall"] == 50

    async def test_dimension_mismatch(self, backend):
        backend["embed"].return_value = [0.0, 1.0]
        with pytest.raises(ValueError, match="维度"):
            await retrieval.search_knowledge_detailed("q")

    async def test_split_searches_each_clause(self, backend):
        result = await retrieval.search_knowledge_detailed(
            "退货政策是什么，运费由谁承担", strategy="hybrid", top_k=4, split=True,
        )
        assert [c["kind"] for c in backend["calls"]] == ["hybrid", "hybrid"]
        assert [h["id"] for h in result["evidence"]] == [10, 20, 11, 21]

    async def test_rewrite_feeds_lexical_query(self, backend, monkeypatch):
        understand = AsyncMock(return_value={"standard": "标准问法", "expanded": ["同义词"]})
        monkeypatch.setattr(retrieval.query_understanding, "understand", understand)

        await retrieval.search_knowledge_detailed("原始", strategy="bm25", rewrite=True)

        understand.assert_awaited_once_with("原始")
        assert backend["calls"][0]["args"][0] == "标准问法 同义词"

    async def test_hybrid_rerank(self, backend, monkeypatch):
        rerank = AsyncMock(side_effect=lambda query, hits, top_k: [
            {**hits[0], "rerank_score": 0.8},
            {**hits[1], "rerank_score": 0.1},
        ])
        monkeypatch.setattr(retrieval.rerank, "rerank_hits", rerank)

        result = await retrieval.search_knowledge_detailed("q", strategy="hybrid_rerank", top_k=2)

        assert backend["calls"][0]["args"][2] == 50  # 精排策略按 recall_top_k 召回
        query, hits, top_k = rerank.await_args.args
        assert (query, len(hits), top_k) == ("q", 3, 2)
        assert [h["id"] for h in result["candidates"]] == [10, 11]
        assert [h["id"] for h in result["evidence"]] == [10]

    async def test_search_knowledge_returns_evidence_only(self, backend):
        assert await retrieval.search_knowledge("q", top_k=1) == [make_hit(10)]


class TestBuildPolicyQueries:
    async def test_filters_and_limits(self):
        async def expand(query):
            return [
                "退货运费谁出",
                123,
                "  ",
                "退货运费谁出",
                "MH-X9 能退吗",
                "x" * 201,
                "ORD-1 能退吗",
                "第四条不会被采纳",
            ]

        queries = await retrieval.build_policy_queries(
            "MH-A1 怎么退货", {"order_id": "ORD-1"}, expand,
        )

        assert queries == ["MH-A1 怎么退货", "退货运费谁出", "ORD-1 能退吗"]

    async def test_order_id_not_allowed_without_order(self):
        async def expand(query):
            return ["ORD-1 能退吗"]

        assert await retrieval.build_policy_queries("怎么退货", None, expand) == ["怎么退货"]

    async def test_rejects_non_list(self):
        async def expand(query):
            return "oops"

        with pytest.raises(ValueError, match="列表"):
            await retrieval.build_policy_queries("q", None, expand)


def policy_hit(hit_id, score, **overrides):
    return make_hit(hit_id, score, **overrides)


async def one_expansion(query):
    return ["扩展问法"]


async def test_retrieve_policy_merges_filters_and_numbers():
    results = {
        "原问题": [
            policy_hit(1, 0.5),
            policy_hit(2, 0.2),
            policy_hit(3, 0.9, answer=" "),
            policy_hit(6, True),
            {"id": None, "rerank_score": 0.9},
            "bad",
        ],
        "扩展问法": [
            policy_hit(1, 0.8),
            policy_hit(4, 0.6, section_path=""),
            policy_hit(5, 0.4),
        ],
    }

    async def search(query):
        return results[query]

    queries, citations = await retrieval.retrieve_policy("原问题", None, one_expansion, search)

    assert queries == ["原问题", "扩展问法"]
    assert [(c["id"], c["rerank_score"], c["n"]) for c in citations] == [(1, 0.8, 1), (5, 0.4, 2)]


async def test_retrieve_policy_caps_at_five_and_ignores_bad_results():
    async def search(query):
        if query == "扩展问法":
            return None
        return [policy_hit(i, 0.3 + i / 100) for i in range(8)]

    _, citations = await retrieval.retrieve_policy("原问题", None, one_expansion, search)

    assert [c["id"] for c in citations] == [7, 6, 5, 4, 3]
    assert [c["n"] for c in citations] == [1, 2, 3, 4, 5]


class TestRetrievePolicyDetailed:
    async def test_global_rerank_with_normalized_candidates(self):
        async def search(query):
            return {"candidates": [policy_hit(1, 0.9, extra="drop"), policy_hit(2, 0.4)]}

        rerank_all = AsyncMock(return_value=[policy_hit(1, 0.7), policy_hit(2, 0.1)])

        queries, result = await retrieval.retrieve_policy_detailed(
            "原问题", None, one_expansion, search, rerank_all,
        )

        assert queries == ["原问题", "扩展问法"]
        query, candidates, top_k = rerank_all.await_args.args
        assert (query, top_k) == ("原问题", 5)
        assert candidates == [
            {"id": 1, "question": "q1", "answer": "a1", "section_path": "售后/退货"},
            {"id": 2, "question": "q2", "answer": "a2", "section_path": "售后/退货"},
        ]
        assert [h["id"] for h in result["evidence"]] == [1]

    async def test_empty_candidates_skip_rerank(self):
        async def search(query):
            return {"candidates": []}

        rerank_all = AsyncMock()
        _, result = await retrieval.retrieve_policy_detailed("q", None, one_expansion, search, rerank_all)
        assert result == {"candidates": [], "evidence": []}
        rerank_all.assert_not_awaited()

    async def test_conflicting_content_rejected(self):
        answers = iter(["版本一", "版本二"])

        async def search(query):
            return {"candidates": [policy_hit(1, 0.9, answer=next(answers))]}

        with pytest.raises(ValueError, match="不同内容"):
            await retrieval.retrieve_policy_detailed("q", None, one_expansion, search, AsyncMock())

    @pytest.mark.parametrize(
        "result,message",
        [
            ("bad", "字典"),
            ({"candidates": None}, "候选列表"),
            ({"candidates": [policy_hit(1, 0.9, answer="")]}, "正文或来源"),
            ({"candidates": [policy_hit(1, 0.9, section_path=" ")]}, "正文或来源"),
        ],
    )
    async def test_invalid_search_result(self, result, message):
        async def search(query):
            return result

        with pytest.raises(ValueError, match=message):
            await retrieval.retrieve_policy_detailed("q", None, one_expansion, search, AsyncMock())
