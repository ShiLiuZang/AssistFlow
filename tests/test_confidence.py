"""app.core.confidence：精排去重、置信度打分与证据闸门。"""
import math

import pytest

from app.core.confidence import (
    compute_evidence_confidence,
    evidence_gate,
    ranked_hits,
    snapshot_from_hits,
)


def hit(hit_id, score, question="问题", answer="答案", **extra):
    return {
        "id": hit_id,
        "rerank_score": score,
        "question": question,
        "answer": answer,
        **extra,
    }


class TestRankedHits:
    def test_sorts_desc_and_keeps_highest_duplicate(self):
        hits = [hit(1, 0.2), hit(2, 0.8), hit(1, 0.6)]

        ranked = ranked_hits(hits)

        assert [(h["id"], h["rerank_score"]) for h in ranked] == [(2, 0.8), (1, 0.6)]

    def test_tie_broken_by_id_string(self):
        ranked = ranked_hits([hit("b", 0.5), hit("a", 0.5)])
        assert [h["id"] for h in ranked] == ["a", "b"]

    def test_returns_copies(self):
        original = hit(1, 0.5, meta={"k": 1})
        ranked = ranked_hits([original])
        ranked[0]["meta"]["k"] = 2
        assert original["meta"]["k"] == 1

    @pytest.mark.parametrize("bad_id", [None, "", "  ", True, 1.5])
    def test_rejects_invalid_id(self, bad_id):
        with pytest.raises(ValueError):
            ranked_hits([hit(bad_id, 0.5)])

    @pytest.mark.parametrize("bad_score", [None, -0.1, 1.1, math.nan, math.inf, True, "0.5"])
    def test_rejects_invalid_score(self, bad_score):
        with pytest.raises(ValueError):
            ranked_hits([hit(1, bad_score)])

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            ranked_hits(["not a dict"])


class TestComputeEvidenceConfidence:
    def test_empty_hits(self):
        result = compute_evidence_confidence([])
        assert result["score"] == 0
        assert result["signals"] == {
            "top1_score": 0.0,
            "valid_count": 0,
            "margin": 0.0,
            "key_clause_hit": False,
        }

    def test_weighted_score(self):
        hits = [
            hit(1, 0.9, question="退货政策"),
            hit(2, 0.5),
            hit(3, 0.1),
        ]

        result = compute_evidence_confidence(hits)

        signals = result["signals"]
        assert signals["top1_score"] == 0.9
        assert signals["valid_count"] == 2
        assert signals["margin"] == pytest.approx(0.4)
        assert signals["key_clause_hit"] is True
        expected = 0.5 * 0.9 + 0.2 * 2 / 3 + 0.2 * 0.4 + 0.1
        assert result["score"] == round(expected, 4)

    def test_single_hit_margin_equals_top1(self):
        result = compute_evidence_confidence([hit(1, 0.7)])
        assert result["signals"]["margin"] == 0.7

    def test_key_clause_only_checks_top3(self):
        hits = [hit(i, 0.9 - i * 0.1) for i in range(3)]
        hits.append(hit(9, 0.1, answer="运费由商家承担"))
        assert compute_evidence_confidence(hits)["signals"]["key_clause_hit"] is False

    def test_rejects_non_string_text(self):
        with pytest.raises(ValueError):
            compute_evidence_confidence([hit(1, 0.5, answer=None)])


def test_snapshot_keeps_top3_selected_fields():
    hits = [hit(i, i / 10, section_path=f"s{i}", extra="drop") for i in range(1, 6)]

    snapshot = snapshot_from_hits(hits)

    assert [item["id"] for item in snapshot] == [5, 4, 3]
    assert set(snapshot[0]) == {"id", "question", "answer", "section_path", "rerank_score"}


class TestEvidenceGate:
    @staticmethod
    def checker(result):
        calls = []

        async def check(question, evidence):
            calls.append((question, evidence))
            if isinstance(result, Exception):
                raise result
            return result

        check.calls = calls
        return check

    GOOD = [hit(1, 0.9, question="退货期限")]

    async def test_passes(self):
        check = self.checker({"useful": True})

        decision = await evidence_gate("q", self.GOOD, 0.5, check, evidence=self.GOOD)

        assert decision.allow is True
        assert decision.reason == "passed"
        assert decision.source is None
        assert check.calls == [("q", self.GOOD)]

    async def test_no_hits(self):
        check = self.checker({"useful": True})
        decision = await evidence_gate("q", [], 0.5, check, evidence=[])
        assert (decision.allow, decision.source, decision.reason) == (
            False, "retrieval_low_conf", "no_evidence",
        )
        assert check.calls == []

    async def test_no_eligible_evidence(self):
        check = self.checker({"useful": True})
        decision = await evidence_gate("q", self.GOOD, 0.5, check, evidence=[])
        assert decision.reason == "no_eligible_evidence"
        assert check.calls == []

    async def test_below_threshold_skips_model_check(self):
        check = self.checker({"useful": True})
        weak = [hit(1, 0.31)]
        decision = await evidence_gate("q", weak, 0.9, check, evidence=weak)
        assert decision.reason == "score_below_threshold"
        assert check.calls == []

    async def test_insufficient(self):
        decision = await evidence_gate(
            "q", self.GOOD, 0.5, self.checker({"useful": False}), evidence=self.GOOD,
        )
        assert (decision.allow, decision.source, decision.reason) == (
            False, "self_check", "insufficient_evidence",
        )

    @pytest.mark.parametrize(
        "result",
        [RuntimeError("timeout"), {"useful": "yes"}, {}, None],
    )
    async def test_check_error(self, result):
        decision = await evidence_gate(
            "q", self.GOOD, 0.5, self.checker(result), evidence=self.GOOD,
        )
        assert decision.reason == "check_error"
        assert decision.source == "self_check"

    async def test_check_receives_copy(self):
        async def mutate(question, evidence):
            evidence[0]["answer"] = "篡改"
            return {"useful": True}

        evidence = [hit(1, 0.9)]
        await evidence_gate("q", evidence, 0.5, mutate, evidence=evidence)
        assert evidence[0]["answer"] == "答案"

    @pytest.mark.parametrize("threshold", [-0.1, 1.5, math.nan, True, "0.5"])
    async def test_rejects_invalid_threshold(self, threshold):
        with pytest.raises(ValueError):
            await evidence_gate(
                "q", self.GOOD, threshold, self.checker({"useful": True}), evidence=self.GOOD,
            )
