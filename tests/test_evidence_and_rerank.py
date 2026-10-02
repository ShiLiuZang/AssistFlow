"""app.core.evidence / sufficiency / rerank：LLM 与重排服务均以替身代替。"""
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core import evidence, rerank, sufficiency


CITATIONS = [
    {"n": 1, "answer": "签收后7天内可无理由退货。"},
    {"n": 2, "answer": "MH-A100 保修一年。"},
]


class TestGroundingChecks:
    def test_number_evidence(self):
        assert evidence.number_evidence([{"id": "a"}, {"id": "b"}]) == [
            {"id": "a", "n": 1},
            {"id": "b", "n": 2},
        ]

    def test_cited_numbers(self):
        assert evidence.cited_numbers("见[1]和[12]，[x]不算") == {1, 12}

    @pytest.mark.parametrize(
        "answer,expected",
        [("可以退货[1]", True), ("可以退货", False), ("见[3]", False), ("  ", False)],
    )
    def test_citations_exist(self, answer, expected):
        assert evidence.citations_exist(answer, CITATIONS) is expected

    @pytest.mark.parametrize(
        "quotes,expected",
        [
            ([{"n": 1, "text": "7天内可无理由退货"}], True),
            ([], False),
            ([{"n": 1, "text": "30天"}], False),
            ([{"n": 9, "text": "7天"}], False),
            ([{"n": 1, "text": "  "}], False),
        ],
    )
    def test_quotes_match(self, quotes, expected):
        assert evidence.quotes_match(quotes, CITATIONS) is expected

    def test_model_codes(self):
        assert evidence.model_codes("mh-a100 和 MH-B2") == {"MH-A100", "MH-B2"}

    def test_grounded_answer(self):
        assert evidence.answer_is_grounded(
            "MH-A100 保修一年[2]",
            [{"n": 2, "text": "保修一年"}],
            CITATIONS,
        )

    def test_cited_without_quote_fails(self):
        assert not evidence.answer_is_grounded(
            "可以退货[1]，保修一年[2]",
            [{"n": 1, "text": "无理由退货"}],
            CITATIONS,
        )

    def test_unsupported_model_code_fails(self):
        assert not evidence.answer_is_grounded(
            "MH-Z9 可以退货[1]",
            [{"n": 1, "text": "无理由退货"}],
            CITATIONS,
        )

    def test_grounded_result_refuses_on_failure(self):
        result = evidence.grounded_result("没有引用", [], CITATIONS)
        assert result == evidence.refusal_result("grounding_failed")
        assert result["answer"] == evidence.REFUSAL

    def test_arrange_head_tail(self):
        items = [{"n": i} for i in range(1, 5)]
        assert [i["n"] for i in evidence.arrange_head_tail(items)] == [1, 3, 4, 2]
        assert evidence.arrange_head_tail(items[:2]) == items[:2]


class FakeStructuredModel:
    """模拟 get_chat_model().with_structured_output(...) 链。"""

    def __init__(self, parsed=None, parsing_error=None):
        self.response = {"raw": object(), "parsed": parsed, "parsing_error": parsing_error}
        self.messages = None

    def with_structured_output(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        return self.response


class TestAnswerFromHits:
    HITS = [{"id": 1, "answer": "签收后7天内可无理由退货。"}]

    async def test_no_hits_refuses_without_model(self, monkeypatch):
        monkeypatch.setattr(evidence, "get_chat_model", lambda: pytest.fail("不应调用模型"))
        result = await evidence.answer_from_hits("q", [])
        assert result["reason"] == "no_evidence"

    async def test_grounded_answer(self, monkeypatch):
        model = FakeStructuredModel(
            evidence.GroundedAnswer(
                answer="可以无理由退货[1]",
                supported=True,
                quotes=[evidence.Quote(n=1, text="7天内可无理由退货")],
            )
        )
        monkeypatch.setattr(evidence, "get_chat_model", lambda: model)

        result = await evidence.answer_from_hits("能退吗", self.HITS, summary_text=" 摘要 ")

        assert result["refused"] is False
        assert result["citations"] == [{"id": 1, "answer": self.HITS[0]["answer"], "n": 1}]
        assert '"conversation_summary"' in model.messages[1][1]

    async def test_unsupported(self, monkeypatch):
        model = FakeStructuredModel(evidence.GroundedAnswer(answer="x", supported=False))
        monkeypatch.setattr(evidence, "get_chat_model", lambda: model)
        result = await evidence.answer_from_hits("q", self.HITS)
        assert result["reason"] == "unsupported_answer"

    async def test_parsing_error_raises(self, monkeypatch):
        model = FakeStructuredModel(parsing_error=ValueError("bad json"))
        monkeypatch.setattr(evidence, "get_chat_model", lambda: model)
        with pytest.raises(ValueError, match="bad json"):
            await evidence.answer_from_hits("q", self.HITS)


class TestCheckSufficient:
    async def test_returns_dict(self, monkeypatch):
        model = FakeStructuredModel(sufficiency.Sufficiency(useful=True))
        monkeypatch.setattr(sufficiency, "get_chat_model", lambda: model)
        assert await sufficiency.check_sufficient("q", []) == {"useful": True}

    async def test_missing_parse_raises(self, monkeypatch):
        model = FakeStructuredModel(parsed=None)
        monkeypatch.setattr(sufficiency, "get_chat_model", lambda: model)
        with pytest.raises(ValueError):
            await sufficiency.check_sufficient("q", [])


class TestRerankMapResult:
    HITS = [{"id": i, "question": f"q{i}", "answer": f"a{i}"} for i in range(3)]

    def test_maps_and_sorts(self):
        result = rerank.map_result(
            self.HITS,
            [{"index": 2, "relevance_score": 0.2}, {"index": 0, "relevance_score": 0.9}],
            top_k=2,
        )
        assert [(h["id"], h["rerank_score"]) for h in result] == [(0, 0.9), (2, 0.2)]

    @pytest.mark.parametrize(
        "items",
        [
            [{"index": 0, "relevance_score": 0.1}],  # 数量不符
            [{"index": 0, "relevance_score": 0.1}, {"index": 0, "relevance_score": 0.2}],
            [{"index": 0, "relevance_score": 0.1}, {"index": 5, "relevance_score": 0.2}],
            [{"index": 0, "relevance_score": 0.1}, {"index": 1.0, "relevance_score": 0.2}],
            [{"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": "nan"}],
        ],
    )
    def test_rejects_bad_results(self, items):
        with pytest.raises(ValueError):
            rerank.map_result(self.HITS, items, top_k=2)


@pytest.mark.parametrize(
    "base,style,expected",
    [
        ("https://api.siliconflow.cn/v1", "auto", "https://api.siliconflow.cn/v1/rerank"),
        ("https://host/", "auto", "https://host/v1/rerank"),
        ("https://dashscope/compatible-api/v1", "auto", "https://dashscope/compatible-api/v1/reranks"),
        ("https://host/v1", "qwen", "https://host/v1/reranks"),
    ],
)
def test_rerank_url(monkeypatch, base, style, expected):
    monkeypatch.setattr(rerank.settings, "rerank_base_url", base)
    monkeypatch.setattr(rerank.settings, "rerank_api_style", style)
    assert rerank.rerank_url() == expected


def test_rerank_url_rejects_unknown_style(monkeypatch):
    monkeypatch.setattr(rerank.settings, "rerank_api_style", "cohere")
    with pytest.raises(ValueError):
        rerank.rerank_url()


class TestRerankHits:
    async def test_empty_hits(self):
        assert await rerank.rerank_hits("q", [], 3) == []

    async def test_requires_api_key(self, monkeypatch):
        monkeypatch.setattr(rerank.settings, "rerank_api_key", "")
        with pytest.raises(ValueError):
            await rerank.rerank_hits("q", [{"question": "a", "answer": "b"}], 1)

    async def test_builds_payload(self, monkeypatch):
        post = AsyncMock(return_value={"results": [{"index": 0, "relevance_score": 0.7}]})
        monkeypatch.setattr(rerank, "post_with_retry", post)
        hits = [{"id": 1, "question": "问", "answer": "答"}]

        result = await rerank.rerank_hits("query", hits, 5)

        _, payload = post.await_args.args
        assert payload["documents"] == ["问\n答"]
        assert payload["top_n"] == 1
        assert result[0]["rerank_score"] == 0.7


class TestPostWithRetry:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr(rerank.asyncio, "sleep", AsyncMock())

    @staticmethod
    def patch_transport(monkeypatch, handler):
        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def client(*args, **kwargs):
            return original(*args, transport=transport, **kwargs)

        monkeypatch.setattr(rerank.httpx, "AsyncClient", client)

    async def test_retries_transient_then_succeeds(self, monkeypatch):
        statuses = iter([503, 429, 200])

        def handler(request):
            return httpx.Response(next(statuses), json={"ok": True})

        self.patch_transport(monkeypatch, handler)
        assert await rerank.post_with_retry("http://x/rerank", {}) == {"ok": True}

    async def test_client_error_not_retried(self, monkeypatch):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(400)

        self.patch_transport(monkeypatch, handler)
        with pytest.raises(httpx.HTTPStatusError):
            await rerank.post_with_retry("http://x/rerank", {})
        assert len(calls) == 1

    async def test_gives_up_after_three_attempts(self, monkeypatch):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ConnectError("down")

        self.patch_transport(monkeypatch, handler)
        with pytest.raises(httpx.ConnectError):
            await rerank.post_with_retry("http://x/rerank", {})
        assert len(calls) == 3
