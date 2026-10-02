"""app.core.evidence：引用编号、原文溯源校验与基于证据的回答生成（LLM 为替身）。"""
import json

import pytest
from langchain_core.messages import AIMessage

from app.core import evidence
from tests.helpers import FakeStructuredModel, patch_model

CITATIONS = [
    {"n": 1, "answer": "签收后7天内可无理由退货。"},
    {"n": 2, "answer": "MH-A100 保修一年。"},
]


def test_number_evidence_keeps_fields():
    assert evidence.number_evidence([{"id": "a"}, {"id": "b", "x": 1}]) == [
        {"id": "a", "n": 1},
        {"id": "b", "x": 1, "n": 2},
    ]


def test_cited_numbers():
    assert evidence.cited_numbers("见[1]和[12]，[x]、[ 3] 不算，[1] 重复") == {1, 12}


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("可以退货[1]", True),
        ("[1][2]", True),
        ("可以退货", False),
        ("见[3]", False),
        ("见[1][3]", False),
        ("   ", False),
    ],
)
def test_citations_exist(answer, expected):
    assert evidence.citations_exist(answer, CITATIONS) is expected


@pytest.mark.parametrize(
    "quotes,expected",
    [
        ([{"n": 1, "text": "7天内可无理由退货"}], True),
        ([{"n": 1, "text": "  7天内  "}], True),
        ([{"n": 1, "text": "7天"}, {"n": 2, "text": "保修一年"}], True),
        ([], False),
        ([{"n": 1, "text": "30天"}], False),
        ([{"n": 2, "text": "7天"}], False),
        ([{"n": 9, "text": "7天"}], False),
        ([{"n": 1, "text": "  "}], False),
        ([{"n": 1}], False),
    ],
)
def test_quotes_match(quotes, expected):
    assert evidence.quotes_match(quotes, CITATIONS) is expected


def test_model_codes_case_insensitive():
    assert evidence.model_codes("mh-a100 和 MH-B2，还有 XMH-") == {"MH-A100", "MH-B2"}


class TestAnswerIsGrounded:
    def test_grounded(self):
        assert evidence.answer_is_grounded(
            "MH-A100 保修一年[2]", [{"n": 2, "text": "保修一年"}], CITATIONS,
        )

    def test_unknown_citation(self):
        assert not evidence.answer_is_grounded("见[5]", [{"n": 1, "text": "7天"}], CITATIONS)

    def test_quote_not_in_source(self):
        assert not evidence.answer_is_grounded("可退[1]", [{"n": 1, "text": "15天"}], CITATIONS)

    def test_cited_without_quote(self):
        assert not evidence.answer_is_grounded(
            "可以退货[1]，保修一年[2]", [{"n": 1, "text": "无理由退货"}], CITATIONS,
        )

    def test_model_code_must_appear_in_cited_sources(self):
        # MH-A100 只出现在资料 2，但回答只引用了资料 1
        assert not evidence.answer_is_grounded(
            "MH-A100 可以退货[1]", [{"n": 1, "text": "无理由退货"}], CITATIONS,
        )


def test_refusal_and_grounded_result():
    assert evidence.refusal_result("no_evidence") == {
        "answer": evidence.REFUSAL, "refused": True, "citations": [], "reason": "no_evidence",
    }
    assert evidence.grounded_result("没有引用", [], CITATIONS) == evidence.refusal_result("grounding_failed")
    assert evidence.grounded_result("可退[1]", [{"n": 1, "text": "无理由退货"}], CITATIONS) == {
        "answer": "可退[1]", "refused": False, "citations": CITATIONS, "reason": None,
    }


@pytest.mark.parametrize(
    "count,order",
    [(0, []), (1, [1]), (2, [1, 2]), (3, [1, 3, 2]), (5, [1, 3, 4, 5, 2])],
)
def test_arrange_head_tail(count, order):
    items = [{"n": i} for i in range(1, count + 1)]
    assert [item["n"] for item in evidence.arrange_head_tail(items)] == order


HITS = [
    {"id": 1, "answer": "签收后7天内可无理由退货。"},
    {"id": 2, "answer": "运费由买家承担。"},
    {"id": 3, "answer": "保修一年。"},
]


def grounded(answer="可以无理由退货[1]", supported=True, quotes=None):
    if quotes is None:
        quotes = [evidence.Quote(n=1, text="7天内可无理由退货")]
    return evidence.GroundedAnswer(answer=answer, supported=supported, quotes=quotes)


class TestAnswerFromHits:
    async def test_no_hits_refuses_without_model(self, monkeypatch):
        monkeypatch.setattr(evidence, "get_chat_model", lambda: pytest.fail("不应调用模型"))
        assert (await evidence.answer_from_hits("q", []))["reason"] == "no_evidence"

    async def test_grounded_answer_and_prompt_payload(self, monkeypatch):
        model = patch_model(monkeypatch, evidence, FakeStructuredModel(grounded()))

        result = await evidence.answer_from_hits(
            "能退吗", HITS, order={"order_id": "ORD-1"}, summary_text=" 摘要 ",
        )

        assert result["refused"] is False
        assert result["answer"] == "可以无理由退货[1]"
        assert [c["n"] for c in result["citations"]] == [1, 2, 3]
        assert model.schema is evidence.GroundedAnswer
        system, human = model.calls[0]
        payload = json.loads(human[1])
        assert payload["question"] == "能退吗"
        assert payload["order"] == {"order_id": "ORD-1"}
        assert [item["n"] for item in payload["evidence"]] == [1, 3, 2]
        assert payload["conversation_summary"] == {
            "type": "untrusted_conversation_summary", "text": "摘要",
        }

    async def test_blank_summary_omitted(self, monkeypatch):
        model = patch_model(monkeypatch, evidence, FakeStructuredModel(grounded()))
        await evidence.answer_from_hits("q", HITS, summary_text="   ")
        assert "conversation_summary" not in json.loads(model.calls[0][1][1])

    async def test_unsupported(self, monkeypatch):
        patch_model(monkeypatch, evidence, FakeStructuredModel(grounded(supported=False)))
        assert (await evidence.answer_from_hits("q", HITS))["reason"] == "unsupported_answer"

    async def test_grounding_failure(self, monkeypatch):
        bad = grounded(quotes=[evidence.Quote(n=1, text="三十天")])
        patch_model(monkeypatch, evidence, FakeStructuredModel(bad))
        assert (await evidence.answer_from_hits("q", HITS))["reason"] == "grounding_failed"

    async def test_parsing_error_raises(self, monkeypatch):
        patch_model(monkeypatch, evidence, FakeStructuredModel(parsing_error=ValueError("bad json")))
        with pytest.raises(ValueError, match="bad json"):
            await evidence.answer_from_hits("q", HITS)

    async def test_missing_parse_raises(self, monkeypatch):
        patch_model(monkeypatch, evidence, FakeStructuredModel(parsed=None))
        with pytest.raises(ValueError, match="可解析"):
            await evidence.answer_from_hits("q", HITS)

    async def test_token_usage_recorded_on_span(self, monkeypatch):
        raw = AIMessage(
            content="",
            usage_metadata={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
            response_metadata={"model_name": "m-1"},
        )
        patch_model(monkeypatch, evidence, FakeStructuredModel(grounded(), raw=raw))
        exported = []

        async def sink(payload):
            exported.append(payload)

        from app.core import observability
        observability.configure_trace_sink(sink)

        await evidence.answer_from_hits("q", HITS)

        assert exported[0]["name"] == "answer_model"
        assert exported[0]["model"] == "m-1"
        assert exported[0]["total_tokens"] == 7
