"""评测相关：检索指标、RAG 离线评测、意图评测、阈值校准、问题池归一化。"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core import evaluation, flywheel
from app.core.flywheel_evaluation import calibrate, comparable
from app.core.intent_evaluation import evaluate_intent


def hits(*paths):
    return [{"section_path": path} for path in paths]


class TestRetrievalMetrics:
    def test_recall_and_reciprocal_rank(self):
        result = evaluation.retrieval_metrics(
            hits("x", "a", "y", "b"),
            groups=[["a", "a2"], ["b"], ["c"]],
            k=4,
        )
        assert result == {"recall": 2 / 3, "rr": 0.5}

    def test_only_top_k_considered(self):
        assert evaluation.retrieval_metrics(hits("x", "a"), [["a"]], k=1) == {"recall": 0.0, "rr": 0.0}

    def test_no_groups_means_not_answerable(self):
        assert evaluation.retrieval_metrics(hits("a"), [], k=3) == {"recall": None, "rr": None}

    def test_rejects_k_below_one(self):
        with pytest.raises(ValueError):
            evaluation.retrieval_metrics([], [["a"]], k=0)


CASES = [
    {"id": "c1", "query": "退货多久", "groups": [["退货"]], "should_refuse": False,
     "expected_terms": ["7天", "无理由"]},
    {"id": "c2", "query": "火星配送吗", "groups": [], "should_refuse": True},
]


class TestEvaluate:
    @pytest.fixture
    def fakes(self, monkeypatch):
        searches = []

        async def search(query, strategy, top_k, rewrite, split):
            searches.append((query, strategy, top_k, rewrite, split))
            if strategy == "bm25" and query == "退货多久":
                raise RuntimeError("milvus down")
            return hits("退货") if query == "退货多久" else hits("其他")

        async def answer(query, found):
            if query == "退货多久":
                return {"answer": "7天内可退", "refused": False}
            return {"answer": "无法确认", "refused": True}

        monkeypatch.setattr(evaluation, "search_knowledge", search)
        monkeypatch.setattr(evaluation, "answer_from_hits", answer)
        return searches

    async def test_summary_per_strategy(self, fakes):
        report = await evaluation.evaluate(CASES, k=3)

        assert report["status"] == "evaluated"
        assert set(report["summary"]) == {"bm25", "hybrid", "hybrid_rerank", "vector"}
        vector = report["summary"]["vector"]
        assert vector == {
            "cases": 2,
            "answerable_cases": 1,
            "failures": 0,
            "recall_at_k": 1.0,
            "mrr": 1.0,
            "refusal_accuracy": 1.0,
            "keyword_coverage": 0.5,
        }
        assert all(call[3:] == (False, False) for call in fakes)

    async def test_failures_recorded_not_raised(self, fakes):
        report = await evaluation.evaluate(CASES, k=3)

        bm25 = report["summary"]["bm25"]
        assert bm25["failures"] == 1
        assert bm25["recall_at_k"] == 0.0
        failed = next(row for row in report["details"] if row["strategy"] == "bm25" and row["id"] == "c1")
        assert failed["error"] == "RuntimeError"

    async def test_retrieval_only(self, fakes):
        report = await evaluation.evaluate(CASES, k=3, generate=False)
        assert "refusal_accuracy" not in report["summary"]["vector"]
        assert "answer" not in report["details"][0]

    @pytest.mark.parametrize("cases,k", [([], 5), (CASES, 0)])
    async def test_rejects_invalid_input(self, cases, k):
        with pytest.raises(ValueError):
            await evaluation.evaluate(cases, k=k)


class TestEvaluateIntent:
    def test_accuracy_confusion_and_errors(self):
        cases = [
            {"query": "到哪了", "expected": "物流"},
            {"query": "我要退", "expected": "退款退货"},
            {"query": "你好", "expected": "闲聊"},
        ]
        predictions = [
            {"intent": "物流", "confidence": 0.9},
            {"intent": "售后", "confidence": 0.7},
            {"intent": "闲聊", "confidence": 0.8},
        ]

        result = evaluate_intent(cases, predictions)

        assert result["count"] == 3
        assert result["accuracy"] == pytest.approx(2 / 3)
        assert {"expected": "退款退货", "predicted": "售后", "count": 1} in result["confusion"]
        assert result["errors"] == [{"query": "我要退", "expected": "退款退货", "predicted": "售后"}]

    @pytest.mark.parametrize("cases,predictions", [([], []), ([{"query": "q", "expected": "物流"}], [])])
    def test_rejects_mismatched_lengths(self, cases, predictions):
        with pytest.raises(ValueError):
            evaluate_intent(cases, predictions)

    def test_rejects_unknown_label(self):
        with pytest.raises(ValueError):
            evaluate_intent([{"query": "q", "expected": "未知"}], [{"intent": "物流", "confidence": 1}])


def calib(i, answerable, score):
    return {"id": i, "split": "calibration", "answerable": answerable, "score": score}


class TestCalibrate:
    ROWS = [calib(1, True, 0.9), calib(2, True, 0.6), calib(3, False, 0.5), calib(4, False, 0.2)]

    def test_scans_and_recommends_best_youden(self):
        result = calibrate(self.ROWS, [0.3, 0.55, 0.8])

        assert result["scan"][1] == {"threshold": 0.55, "pass_rate": 1.0, "leak_rate": 0.0, "youden_j": 1.0}
        assert result["recommended"]["threshold"] == 0.55

    def test_tie_prefers_higher_threshold(self):
        rows = [calib(1, True, 0.9), calib(2, False, 0.1)]
        assert calibrate(rows, [0.2, 0.5])["recommended"]["threshold"] == 0.5

    @pytest.mark.parametrize(
        "rows,thresholds",
        [
            ([], [0.5]),
            ([{**calib(1, True, 0.9), "split": "test"}, calib(2, False, 0.1)], [0.5]),
            ([calib(1, True, 0.9), calib(1, False, 0.1)], [0.5]),
            ([calib(1, True, 0.9), calib(2, True, 0.1)], [0.5]),
            ([calib(1, True, 0.9), calib(2, False, 0.1)], []),
            ([calib(1, True, 1.2), calib(2, False, 0.1)], [0.5]),
            ([calib(1, "yes", 0.9), calib(2, False, 0.1)], [0.5]),
            ([calib(1, True, True), calib(2, False, 0.1)], [0.5]),
            ([calib(1, True, 0.9), calib(2, False, 0.1)], [1.5]),
        ],
    )
    def test_rejects_invalid_input(self, rows, thresholds):
        with pytest.raises(ValueError):
            calibrate(rows, thresholds)


def test_comparable_runs():
    base = {"dataset_version": "v1", "case_ids": [1], "config_version": "c", "strategy": "s", "top_k": 5, "x": 1}
    assert comparable(base, {**base, "x": 2})
    assert not comparable(base, {**base, "top_k": 3})


class TestProcessPending:
    @pytest.fixture
    def repo(self, monkeypatch):
        fake = {
            "list_unmatched_questions": AsyncMock(return_value=[
                {"id": 1, "question": "猫窝怎么洗"},
                {"id": 2, "question": "坏的"},
            ]),
            "list_review_candidates": AsyncMock(return_value=[{"id": 10, "question": "清洗"}]),
            "merge_question": AsyncMock(return_value=(None, "created")),
        }
        for name, value in fake.items():
            monkeypatch.setattr(flywheel.repository, name, value)
        return fake

    async def test_counts_actions_and_skips(self, repo):
        async def normalize(question, candidates):
            if question == "坏的":
                return {"question": "  "}
            return {"question": " 猫窝如何清洗 ", "matched_id": 10}

        stats = await flywheel.process_pending(normalize, batch_size=5)

        assert stats["created"] == 1
        assert stats["skipped"] == 1
        assert stats["skipped_reasons"] == {"ValidationError": 1}
        repo["list_unmatched_questions"].assert_awaited_once_with(limit=5)
        assert repo["merge_question"].await_args.kwargs == {
            "pool_id": 1,
            "question": "猫窝如何清洗",
            "suggestion": "",
            "matched_id": 10,
            "offered_ids": {10},
        }

    async def test_truncates_candidates(self, repo):
        repo["list_review_candidates"].return_value = [{"id": i} for i in range(flywheel.MAX_CANDIDATES + 1)]
        seen = []

        async def normalize(question, candidates):
            seen.append(len(candidates))
            return {"question": question}

        stats = await flywheel.process_pending(normalize)

        assert seen == [flywheel.MAX_CANDIDATES] * 2
        assert stats["candidate_truncated"] == 2

    async def test_timeout_skips_item(self, repo):
        async def slow(question, candidates):
            await asyncio.sleep(1)

        stats = await flywheel.process_pending(slow, timeout=0.01)
        assert stats["skipped_reasons"] == {"TimeoutError": 2}

    @pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"batch_size": 0}, {"batch_size": 101}])
    async def test_rejects_invalid_budget(self, kwargs):
        with pytest.raises(ValueError):
            await flywheel.process_pending(AsyncMock(), **kwargs)

    async def test_normalize_with_model(self, monkeypatch):
        from tests.helpers import FakeStructuredModel, patch_model

        model = patch_model(monkeypatch, flywheel, FakeStructuredModel({"question": "标准问", "matched_id": 3}))

        result = await flywheel.normalize_with_model("原话", [{"id": 3}])

        assert result == {"question": "标准问", "suggestion": "", "matched_id": 3}
        assert '"candidates"' in model.calls[0][1][1]
