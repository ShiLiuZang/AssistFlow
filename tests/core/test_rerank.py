"""app.core.rerank：重排结果映射、接口地址、重试策略（HTTP 用 MockTransport）。"""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core import rerank

HITS = [{"id": i, "question": f"q{i}", "answer": f"a{i}", "score": 0.1 * i} for i in range(3)]


class TestMapResult:
    def test_maps_sorts_and_keeps_recall_score(self):
        result = rerank.map_result(
            HITS,
            [{"index": 2, "relevance_score": 0.2}, {"index": 0, "relevance_score": "0.9"}],
            top_k=2,
        )
        assert [(h["id"], h["rerank_score"], h["score"]) for h in result] == [
            (0, 0.9, 0.0), (2, 0.2, 0.2),
        ]

    def test_top_k_larger_than_hits(self):
        result = rerank.map_result(
            HITS[:1], [{"index": 0, "relevance_score": 0.5}], top_k=10,
        )
        assert len(result) == 1

    @pytest.mark.parametrize(
        "items,message",
        [
            ([{"index": 0, "relevance_score": 0.1}], "数量"),
            ([{"index": 0, "relevance_score": 0.1}, {"index": 0, "relevance_score": 0.2}], "重复"),
            ([{"index": 0, "relevance_score": 0.1}, {"index": 5, "relevance_score": 0.2}], "越界"),
            ([{"index": 0, "relevance_score": 0.1}, {"index": -1, "relevance_score": 0.2}], "越界"),
            ([{"index": 0, "relevance_score": 0.1}, {"index": 1.0, "relevance_score": 0.2}], "整数"),
            ([{"index": 0, "relevance_score": 0.1}, {"index": True, "relevance_score": 0.2}], "整数"),
            ([{"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": "nan"}], "有限"),
        ],
    )
    def test_rejects_bad_results(self, items, message):
        with pytest.raises(ValueError, match=message):
            rerank.map_result(HITS, items, top_k=2)

    def test_rejects_non_positive_top_k(self):
        with pytest.raises(ValueError):
            rerank.map_result(HITS, [], top_k=0)


@pytest.mark.parametrize(
    "base,style,expected",
    [
        ("https://api.siliconflow.cn/v1", "auto", "https://api.siliconflow.cn/v1/rerank"),
        ("https://host/", "auto", "https://host/v1/rerank"),
        ("https://host/v2", "singular", "https://host/v2/rerank"),
        ("https://dashscope/compatible-api/v1", "auto", "https://dashscope/compatible-api/v1/reranks"),
        ("https://host/v1", " QWEN ", "https://host/v1/reranks"),
        ("https://host/v1", "dashscope", "https://host/v1/reranks"),
    ],
)
def test_rerank_url(monkeypatch, base, style, expected):
    monkeypatch.setattr(rerank.settings, "rerank_base_url", base)
    monkeypatch.setattr(rerank.settings, "rerank_api_style", style)
    assert rerank.rerank_url() == expected


def test_rerank_url_rejects_unknown_style(monkeypatch):
    monkeypatch.setattr(rerank.settings, "rerank_api_style", "cohere")
    with pytest.raises(ValueError, match="RERANK_API_STYLE"):
        rerank.rerank_url()


class TestRerankHits:
    async def test_empty_hits(self):
        assert await rerank.rerank_hits("q", [], 3) == []

    async def test_rejects_non_positive_top_k(self):
        with pytest.raises(ValueError):
            await rerank.rerank_hits("q", HITS, 0)

    async def test_requires_api_key(self, monkeypatch):
        monkeypatch.setattr(rerank.settings, "rerank_api_key", "")
        with pytest.raises(ValueError, match="RERANK_API_KEY"):
            await rerank.rerank_hits("q", HITS, 1)

    async def test_builds_payload(self, monkeypatch):
        post = AsyncMock(return_value={"results": [{"index": 1, "relevance_score": 0.7}]})
        monkeypatch.setattr(rerank, "post_with_retry", post)

        result = await rerank.rerank_hits("query", HITS[:2], 1)

        url, payload = post.await_args.args
        assert url == "http://rerank.invalid/v1/rerank"
        assert payload == {
            "model": rerank.settings.rerank_model,
            "query": "query",
            "documents": ["q0\na0", "q1\na1"],
            "top_n": 1,
        }
        assert [(h["id"], h["rerank_score"]) for h in result] == [(1, 0.7)]


class TestPostWithRetry:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        sleep = AsyncMock()
        monkeypatch.setattr(rerank.asyncio, "sleep", sleep)
        return sleep

    @pytest.fixture
    def transport(self, monkeypatch):
        requests = []

        def install(handler):
            def recording(request):
                requests.append(request)
                return handler(request)

            original = httpx.AsyncClient
            monkeypatch.setattr(
                rerank.httpx, "AsyncClient",
                lambda *a, **k: original(*a, transport=httpx.MockTransport(recording), **k),
            )
            return requests

        return install

    async def test_sends_auth_and_json(self, transport):
        requests = transport(lambda r: httpx.Response(200, json={"ok": True}))

        assert await rerank.post_with_retry("http://x/rerank", {"a": 1}) == {"ok": True}
        assert requests[0].headers["Authorization"] == "Bearer test-key"
        assert json.loads(requests[0].content) == {"a": 1}

    async def test_retries_transient_with_backoff(self, transport, no_sleep):
        statuses = iter([503, 429, 200])
        requests = transport(lambda r: httpx.Response(next(statuses), json={"ok": True}))

        assert await rerank.post_with_retry("http://x/rerank", {}) == {"ok": True}
        assert len(requests) == 3
        assert [c.args[0] for c in no_sleep.await_args_list] == [0.5, 1.0]

    async def test_client_error_not_retried(self, transport):
        requests = transport(lambda r: httpx.Response(400))
        with pytest.raises(httpx.HTTPStatusError):
            await rerank.post_with_retry("http://x/rerank", {})
        assert len(requests) == 1

    async def test_gives_up_after_three_attempts(self, transport):
        def down(request):
            raise httpx.ConnectError("down")

        requests = transport(down)
        with pytest.raises(httpx.ConnectError):
            await rerank.post_with_retry("http://x/rerank", {})
        assert len(requests) == 3
