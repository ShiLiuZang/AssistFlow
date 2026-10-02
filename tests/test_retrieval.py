"""app.core.retrieval：检索编排，Milvus / 向量化 / 重排均以替身代替。"""
from unittest.mock import AsyncMock

import pytest

from app.core import retrieval
from app.kb import milvus_client


def hit(hit_id, score=None, **extra):
    data = {"id": hit_id, "question": f"q{hit_id}", "answer": f"a{hit_id}", **extra}
    if score is not None:
        data["rerank_score"] = score
    return data


class TestSplitRankedHits:
    def test_filters_evidence_by_min_score(self):
        result = retrieval.split_ranked_hits(
            [hit(1, 0.2), hit(2, 0.9), hit(3, 0.3)],
            min_score=0.3,
        )
        assert [h["id"] for h in result["candidates"]] == [2, 3, 1]
        assert [h["id"] for h in result["evidence"]] == [2, 3]

    def test_evidence_is_independent_copy(self):
        result = retrieval.split_ranked_hits([hit(1, 0.9)], min_score=0.3)
        result["evidence"][0]["answer"] = "changed"
        assert result["candidates"][0]["answer"] == "a1"

    @pytest.mark.parametrize("bad", [-1, 2, float("nan"), True, "0.3"])
    def test_rejects_invalid_min_score(self, bad):
        with pytest.raises(ValueError):
            retrieval.split_ranked_hits([], min_score=bad)


class TestSplitClauses:
    def test_splits_on_punctuation(self):
        assert retrieval.split_clauses("退货政策是什么，运费由谁承担？") == [
            "退货政策是什么",
            "运费由谁承担",
        ]

    def test_drops_short_fragments_and_falls_back(self):
        query = "退货政策是什么，好？"
        assert retrieval.split_clauses(query) == [query]


def test_merge_round_robin_interleaves_and_dedups():
    groups = [
        [hit(1), hit(2), hit(3)],
        [hit(2), hit(4)],
        [],
    ]
    assert [h["id"] for h in retrieval.merge_round_robin(groups)] == [1, 2, 4, 3]
    assert retrieval.merge_round_robin([]) == []


@pytest.fixture
def fake_backend(monkeypatch):
    """替换 Milvus 与向量化，记录每次检索调用。"""
    calls = []

    async def acall(fn):
        return fn()

    def make_search(kind):
        def search(client, *args, **kwargs):
            calls.append((kind, args, kwargs))
            n = len(calls)
            return [hit(n * 10 + i) for i in range(3)]
        return search

    monkeypatch.setattr(milvus_client, "acall", acall)
    monkeypatch.setattr(milvus_client, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(milvus_client, "dense_search", make_search("dense"))
    monkeypatch.setattr(milvus_client, "bm25_search", make_search("bm25"))
    monkeypatch.setattr(milvus_client, "hybrid_search", make_search("hybrid"))
    embed = AsyncMock(return_value=[0.0] * milvus_client.DIM)
    monkeypatch.setattr(retrieval.embeddings, "embed_query", embed)
    return {"calls": calls, "embed": embed}


class TestSearchKnowledgeDetailed:
    async def test_rejects_unknown_strategy(self):
        with pytest.raises(ValueError):
            await retrieval.search_knowledge_detailed("q", strategy="magic", client=object())

    async def test_rejects_non_positive_top_k(self):
        with pytest.raises(ValueError):
            await retrieval.search_knowledge_detailed("q", top_k=0, client=object())

    async def test_vector_strategy(self, fake_backend):
        result = await retrieval.search_knowledge_detailed(
            "退货政策", strategy="vector", top_k=2, client=object(), category="售后",
        )

        assert result["candidates"] is None
        assert [h["id"] for h in result["evidence"]] == [10, 11]
        kind, args, kwargs = fake_backend["calls"][0]
        assert kind == "dense"
        assert args[1] == 2
        assert kwargs["category"] == "售后"
        fake_backend["embed"].assert_awaited_once_with("退货政策")

    async def test_bm25_skips_embedding(self, fake_backend):
        await retrieval.search_knowledge_detailed("退货", strategy="bm25", client=object())
        assert fake_backend["calls"][0][0] == "bm25"
        fake_backend["embed"].assert_not_awaited()

    async def test_dimension_mismatch(self, fake_backend):
        fake_backend["embed"].return_value = [0.0, 1.0]
        with pytest.raises(ValueError, match="维度"):
            await retrieval.search_knowledge_detailed("q", client=object())

    async def test_split_searches_each_clause(self, fake_backend):
        result = await retrieval.search_knowledge_detailed(
            "退货政策是什么，运费由谁承担",
            strategy="hybrid",
            top_k=4,
            client=object(),
            split=True,
        )
        assert [c[0] for c in fake_backend["calls"]] == ["hybrid", "hybrid"]
        assert [h["id"] for h in result["evidence"]] == [10, 20, 11, 21]

    async def test_rewrite_uses_understood_query(self, fake_backend, monkeypatch):
        understand = AsyncMock(return_value={"standard": "标准问法", "expanded": ["同义词"]})
        monkeypatch.setattr(retrieval.query_understanding, "understand", understand)

        await retrieval.search_knowledge_detailed(
            "原始", strategy="bm25", client=object(), rewrite=True,
        )

        _, args, _ = fake_backend["calls"][0]
        assert args[0] == "标准问法 同义词"

    async def test_hybrid_rerank(self, fake_backend, monkeypatch):
        async def rerank_hits(query, hits, top_k):
            return [
                {**hits[0], "rerank_score": 0.8},
                {**hits[1], "rerank_score": 0.1},
            ]

        monkeypatch.setattr(retrieval.rerank, "rerank_hits", rerank_hits)

        result = await retrieval.search_knowledge_detailed(
            "q", strategy="hybrid_rerank", top_k=2, client=object(),
        )

        # 精排策略按 recall_top_k 召回
        assert fake_backend["calls"][0][1][2] == 50
        assert [h["id"] for h in result["candidates"]] == [10, 11]
        assert [h["id"] for h in result["evidence"]] == [10]

    async def test_search_knowledge_returns_evidence(self, fake_backend):
        evidence = await retrieval.search_knowledge("q", top_k=1, client=object())
        assert [h["id"] for h in evidence] == [10]


class TestBuildPolicyQueries:
    async def test_filters_and_limits(self):
        async def expand(query):
            return [
                "退货运费谁出",
                123,
                "",
                "退货运费谁出",
                "MH-X9 能退吗",  # 引入原问题没有的型号
                "x" * 201,
                "ORD-1 能退吗",  # 订单号允许
                "第四条不会被采纳",
            ]

        queries = await retrieval.build_policy_queries(
            "MH-A1 怎么退货", {"order_id": "ORD-1"}, expand,
        )

        assert queries == ["MH-A1 怎么退货", "退货运费谁出", "ORD-1 能退吗"]

    async def test_rejects_non_list(self):
        async def expand(query):
            return "oops"

        with pytest.raises(ValueError):
            await retrieval.build_policy_queries("q", None, expand)


def policy_hit(hit_id, score, **overrides):
    return {
        "id": hit_id,
        "question": f"q{hit_id}",
        "answer": f"a{hit_id}",
        "section_path": "售后/退货",
        "rerank_score": score,
        **overrides,
    }


async def no_expand(query):
    return ["扩展问法"]


async def test_retrieve_policy_merges_and_numbers():
    results = {
        "原问题": [
            policy_hit(1, 0.5),
            policy_hit(2, 0.2),  # 低于 0.3
            policy_hit(3, 0.9, answer=" "),  # 空答案
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

    queries, citations = await retrieval.retrieve_policy("原问题", None, no_expand, search)

    assert queries == ["原问题", "扩展问法"]
    assert [(c["id"], c["rerank_score"], c["n"]) for c in citations] == [
        (1, 0.8, 1),
        (5, 0.4, 2),
    ]


class TestRetrievePolicyDetailed:
    async def test_global_rerank(self):
        async def search(query):
            return {"candidates": [policy_hit(1, 0.9), policy_hit(2, 0.4)]}

        rerank_all = AsyncMock(
            return_value=[policy_hit(1, 0.7), policy_hit(2, 0.1)],
        )

        queries, result = await retrieval.retrieve_policy_detailed(
            "原问题", None, no_expand, search, rerank_all,
        )

        assert queries == ["原问题", "扩展问法"]
        query, candidates, top_k = rerank_all.await_args.args
        assert query == "原问题"
        assert top_k == 5
        # 送入精排的是去掉旧分数的标准化候选
        assert all("rerank_score" not in c for c in candidates)
        assert [h["id"] for h in result["evidence"]] == [1]

    async def test_empty_candidates_skip_rerank(self):
        async def search(query):
            return {"candidates": []}

        rerank_all = AsyncMock()
        _, result = await retrieval.retrieve_policy_detailed(
            "q", None, no_expand, search, rerank_all,
        )
        assert result == {"candidates": [], "evidence": []}
        rerank_all.assert_not_awaited()

    async def test_conflicting_content_rejected(self):
        answers = iter(["版本一", "版本二"])

        async def search(query):
            return {"candidates": [policy_hit(1, 0.9, answer=next(answers))]}

        with pytest.raises(ValueError, match="不同内容"):
            await retrieval.retrieve_policy_detailed(
                "q", None, no_expand, search, AsyncMock(),
            )

    @pytest.mark.parametrize(
        "result",
        ["bad", {"candidates": None}, {"candidates": [policy_hit(1, 0.9, answer="")]}],
    )
    async def test_invalid_search_result(self, result):
        async def search(query):
            return result

        with pytest.raises(ValueError):
            await retrieval.retrieve_policy_detailed(
                "q", None, no_expand, search, AsyncMock(),
            )
