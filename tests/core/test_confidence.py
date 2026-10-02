"""app.core.confidence：精排去重、置信度打分与证据闸门。"""
import math

import pytest

from app.core.confidence import (
    KEY_TERMS,
    compute_evidence_confidence,
    evidence_gate,
    ranked_hits,
    snapshot_from_hits,
)
from tests.helpers import make_hit


class TestRankedHits:
    def test_sorted_by_score_desc(self):
        ranked = ranked_hits([make_hit(1, 0.2), make_hit(2, 0.8), make_hit(3, 0.5)])
        assert [h["id"] for h in ranked] == [2, 3, 1]

    def test_duplicate_id_keeps_highest_score(self):
        ranked = ranked_hits([make_hit(1, 0.2), make_hit(1, 0.6), make_hit(1, 0.4)])
        assert ranked == [make_hit(1, 0.6)]

    def test_ties_broken_by_id_string(self):
        ranked = ranked_hits([make_hit("b", 0.5), make_hit("a", 0.5), make_hit(10, 0.5)])
        assert [h["id"] for h in ranked] == [10, "a", "b"]

    def test_returns_deep_copies(self):
        original = make_hit(1, 0.5, meta={"k": 1})
        ranked_hits([original])[0]["meta"]["k"] = 2
        assert original["meta"]["k"] == 1

    def test_accepts_boundary_scores(self):
        assert len(ranked_hits([make_hit(1, 0), make_hit(2, 1)])) == 2

    @pytest.mark.parametrize("bad_id", [None, "", "   ", True, 1.5, [1]])
    def test_rejects_invalid_id(self, bad_id):
        with pytest.raises(ValueError, match="ID"):
            ranked_hits([make_hit(bad_id, 0.5)])

    @pytest.mark.parametrize(
        "bad_score", [None, -0.01, 1.01, math.nan, math.inf, True, "0.5"],
    )
    def test_rejects_invalid_score(self, bad_score):
        with pytest.raises(ValueError, match="精排分数"):
            ranked_hits([make_hit(1, bad_score)])

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError, match="字典"):
            ranked_hits([("id", 1)])


class TestComputeEvidenceConfidence:
    def test_empty(self):
        assert compute_evidence_confidence([]) == {
            "score": 0.0,
            "signals": {
                "top1_score": 0.0,
                "valid_count": 0,
                "margin": 0.0,
                "key_clause_hit": False,
            },
        }

    def test_weighted_formula(self):
        result = compute_evidence_confidence([
            make_hit(1, 0.9, question="退货政策"),
            make_hit(2, 0.5),
            make_hit(3, 0.1),
        ])

        assert result["signals"] == {
            "top1_score": 0.9,
            "valid_count": 2,
            "margin": pytest.approx(0.4),
            "key_clause_hit": True,
        }
        expected = 0.5 * 0.9 + 0.2 * 2 / 3 + 0.2 * 0.4 + 0.1
        assert result["score"] == round(expected, 4)

    def test_valid_count_capped_at_three_in_score(self):
        hits = [make_hit(i, 0.5) for i in range(5)]
        result = compute_evidence_confidence(hits)
        assert result["signals"]["valid_count"] == 5
        assert result["score"] == round(0.5 * 0.5 + 0.2 + 0.0, 4)

    def test_valid_count_threshold_inclusive(self):
        result = compute_evidence_confidence([make_hit(1, 0.3), make_hit(2, 0.29)])
        assert result["signals"]["valid_count"] == 1

    def test_single_hit_margin_is_top1(self):
        assert compute_evidence_confidence([make_hit(1, 0.7)])["signals"]["margin"] == 0.7

    def test_duplicates_do_not_shrink_margin(self):
        result = compute_evidence_confidence([make_hit(1, 0.8), make_hit(1, 0.8)])
        assert result["signals"]["margin"] == 0.8

    @pytest.mark.parametrize("term", KEY_TERMS)
    def test_each_key_term_detected_in_answer(self, term):
        result = compute_evidence_confidence([make_hit(1, 0.5, answer=f"关于{term}的说明")])
        assert result["signals"]["key_clause_hit"] is True

    def test_key_term_only_checked_in_top3(self):
        hits = [make_hit(i, 0.9 - i * 0.1) for i in range(3)]
        hits.append(make_hit(9, 0.05, answer="运费由商家承担"))
        assert compute_evidence_confidence(hits)["signals"]["key_clause_hit"] is False

    def test_rejects_non_string_text(self):
        with pytest.raises(ValueError, match="字符串"):
            compute_evidence_confidence([make_hit(1, 0.5, answer=None)])

    def test_missing_question_and_answer_treated_as_empty(self):
        result = compute_evidence_confidence([{"id": 1, "rerank_score": 0.4}])
        assert result["signals"]["key_clause_hit"] is False


def test_snapshot_keeps_top3_and_selected_fields():
    hits = [make_hit(i, i / 10, extra="drop") for i in range(1, 6)]

    snapshot = snapshot_from_hits(hits)

    assert [item["id"] for item in snapshot] == [5, 4, 3]
    assert snapshot[0] == {
        "id": 5,
        "question": "q5",
        "answer": "a5",
        "section_path": "售后/退货",
        "rerank_score": 0.5,
    }


def test_snapshot_fills_missing_fields_with_none():
    assert snapshot_from_hits([{"id": 1, "rerank_score": 0.5}]) == [{
        "id": 1, "question": None, "answer": None, "section_path": None, "rerank_score": 0.5,
    }]


def checker(result):
    calls = []

    async def check(question, evidence):
        calls.append((question, evidence))
        if isinstance(result, Exception):
            raise result
        return result

    check.calls = calls
    return check


GOOD = [make_hit(1, 0.9, question="退货期限")]


class TestEvidenceGate:
    async def test_passes(self):
        check = checker({"useful": True})

        decision = await evidence_gate("能退吗", GOOD, 0.5, check, evidence=GOOD)

        assert (decision.allow, decision.source, decision.reason) == (True, None, "passed")
        assert decision.snapshot[0]["id"] == 1
        assert check.calls == [("能退吗", GOOD)]

    async def test_no_hits(self):
        check = checker({"useful": True})
        decision = await evidence_gate("q", [], 0.5, check, evidence=[])
        assert (decision.allow, decision.source, decision.reason) == (
            False, "retrieval_low_conf", "no_evidence",
        )
        assert check.calls == []

    async def test_no_eligible_evidence(self):
        check = checker({"useful": True})
        decision = await evidence_gate("q", GOOD, 0.5, check, evidence=[])
        assert decision.reason == "no_eligible_evidence"
        assert check.calls == []

    async def test_below_threshold_skips_model_check(self):
        check = checker({"useful": True})
        weak = [make_hit(1, 0.31)]
        decision = await evidence_gate("q", weak, 0.9, check, evidence=weak)
        assert decision.reason == "score_below_threshold"
        assert decision.confidence["score"] < 0.9
        assert check.calls == []

    async def test_threshold_equal_to_score_passes(self):
        score = (await evidence_gate("q", GOOD, 0, checker({"useful": True}), evidence=GOOD)).confidence["score"]
        decision = await evidence_gate("q", GOOD, score, checker({"useful": True}), evidence=GOOD)
        assert decision.allow is True

    async def test_insufficient(self):
        decision = await evidence_gate("q", GOOD, 0.5, checker({"useful": False}), evidence=GOOD)
        assert (decision.allow, decision.source, decision.reason) == (
            False, "self_check", "insufficient_evidence",
        )

    @pytest.mark.parametrize(
        "result",
        [TimeoutError(), RuntimeError("boom"), {"useful": "yes"}, {"useful": 1}, {}, None, [True]],
    )
    async def test_check_error(self, result):
        decision = await evidence_gate("q", GOOD, 0.5, checker(result), evidence=GOOD)
        assert (decision.allow, decision.source, decision.reason) == (
            False, "self_check", "check_error",
        )

    async def test_check_receives_independent_copy(self):
        async def mutate(question, evidence):
            evidence[0]["answer"] = "篡改"
            return {"useful": True}

        evidence = [make_hit(1, 0.9)]
        await evidence_gate("q", evidence, 0.5, mutate, evidence=evidence)
        assert evidence[0]["answer"] == "a1"

    @pytest.mark.parametrize("threshold", [-0.1, 1.5, math.nan, math.inf, True, "0.5", None])
    async def test_rejects_invalid_threshold(self, threshold):
        with pytest.raises(ValueError, match="阈值"):
            await evidence_gate("q", GOOD, threshold, checker({"useful": True}), evidence=GOOD)
