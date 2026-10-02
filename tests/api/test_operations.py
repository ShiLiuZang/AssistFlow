"""运营类接口：审核队列、知识检索与评测、观测报表、主题分布、后台作业、结构化提取、后台总览。"""
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api import admin, extract, jobs as jobs_api, knowledge, observability, review, topics
from app.config import settings
from app.core import jobs
from app.core.taxonomy import TOPIC_NAMES
from app.schemas.extract import AfterSalesTicket, RequestType
from tests.helpers import FakeStructuredModel, make_hit, patch_model


def review_row(status="pending", **extra):
    return {"id": 3, "question": "能退吗", "suggestion": "可以", "status": status, **extra}


class TestReview:
    @pytest.mark.parametrize("label,status", [("", None), ("待审", "pending"), ("发布中", "publishing")])
    def test_queue_filters_by_label(self, client, repo, label, status):
        repo.set("list_review_queue", return_value=[review_row()])
        item, = client.get("/api/review/queue", params={"status": label}).json()["items"]
        assert repo.list_review_queue.await_args.args == (status,)
        assert (item["normalized_question"], item["ai_suggested_answer"], item["review_status"]) == ("能退吗", "可以", "待审")

    def test_queue_rejects_unknown_label(self, client, repo):
        assert client.get("/api/review/queue", params={"status": "pending"}).status_code == 400

    def test_process(self, client, monkeypatch):
        process = AsyncMock(return_value={"processed": 2})
        monkeypatch.setattr(review, "process_pending", process)
        assert client.post("/api/review/process", params={"limit": 5}).json() == {"processed": 2}
        assert process.await_args.kwargs == {"batch_size": 5}
        assert client.post("/api/review/process", params={"limit": 21}).status_code == 422

    def test_detail(self, client, repo):
        repo.set("get_review_detail", return_value=review_row("approved"))
        assert client.get("/api/review/3").json()["review_status"] == "通过"
        repo.get_review_detail.return_value = None
        assert client.get("/api/review/3").status_code == 404

    @pytest.mark.parametrize("error,status", [(None, 200), (LookupError("无"), 404), (ValueError("已处理"), 409)])
    def test_reject(self, client, repo, error, status):
        repo.set("reject_review", return_value=review_row("rejected"), side_effect=error)
        response = client.post("/api/review/3/reject")
        assert response.status_code == status
        assert repo.reject_review.await_args.args == (3, "test-reviewer")

    def test_reject_falls_back_to_local_reviewer(self, client, repo, monkeypatch):
        monkeypatch.setattr(settings, "review_admin_name", "  ")
        repo.set("reject_review", return_value=review_row("rejected"))
        client.post("/api/review/3/reject")
        assert repo.reject_review.await_args.args == (3, "local-reviewer")

    @pytest.fixture
    def approving(self, repo, monkeypatch):
        repo.set("get_review_detail", return_value=review_row())
        repo.set("approve_review", return_value=review_row("publishing"))
        repo.validate = lambda *args: "digest"
        monkeypatch.setattr(review, "validate_review_source", lambda *args: repo.validate(*args))
        repo.publish = AsyncMock(return_value=review_row("approved"))
        monkeypatch.setattr(review, "publish_review", repo.publish)
        return repo

    BODY = {"approved_answer": " 签收7天内可退 ", "source_ref": " policy.md#退货 "}

    def test_approve_publishes(self, client, approving):
        response = client.post("/api/review/3/approve", json=self.BODY)
        assert (response.status_code, response.json()["review_status"]) == (200, "通过")
        assert approving.approve_review.await_args.args == (3, "test-reviewer", "签收7天内可退", "policy.md#退货", "digest")

    def test_approve_publish_failure_returns_202(self, client, approving):
        approving.publish.side_effect = RuntimeError("milvus down")
        approving.get_review_detail.side_effect = [review_row(), None]
        response = client.post("/api/review/3/approve", json=self.BODY)
        assert (response.status_code, response.json()["review_status"]) == (202, "发布中")

    def raise_(self, error):
        def validate(*args):
            raise error
        return validate

    @pytest.mark.parametrize(
        "setup,status",
        [
            (lambda r, t: setattr(r.get_review_detail, "return_value", None), 404),
            (lambda r, t: setattr(r, "validate", t.raise_(ValueError("来源不可信"))), 422),
            (lambda r, t: setattr(r, "validate", t.raise_(OSError())), 503),
            (lambda r, t: setattr(r.approve_review, "side_effect", ValueError("状态已变")), 409),
        ],
    )
    def test_approve_errors(self, client, approving, setup, status):
        setup(approving, self)
        assert client.post("/api/review/3/approve", json=self.BODY).status_code == status
        approving.publish.assert_not_awaited()

    @pytest.mark.parametrize("body", [{"approved_answer": "", "source_ref": "x"}, {"approved_answer": "x"}])
    def test_approve_422_on_body(self, client, approving, body):
        assert client.post("/api/review/3/approve", json=body).status_code == 422

    @pytest.mark.parametrize(
        "error,current,status",
        [(None, None, 200), (LookupError("无"), None, 409), (RuntimeError(), review_row("publishing"), 202),
         (RuntimeError(), None, 404)],
    )
    def test_retry_publish(self, client, approving, error, current, status):
        approving.publish.side_effect = error
        approving.get_review_detail.return_value = current
        assert client.post("/api/review/3/publish").status_code == status


class TestKnowledge:
    def test_search(self, client, monkeypatch):
        search = AsyncMock(return_value=[make_hit(1, 0.9)])
        monkeypatch.setattr(knowledge, "search_knowledge", search)

        response = client.post("/api/knowledge/search", json={"query": "退货", "strategy": "hybrid", "top_k": 3})

        assert response.json()[0]["id"] == 1
        assert search.await_args.kwargs == {
            "query": "退货", "strategy": "hybrid", "top_k": 3, "category": None, "rewrite": False, "split": False,
        }

    @pytest.mark.parametrize("body", [{"query": ""}, {"query": "q", "strategy": "magic"}, {"query": "q", "top_k": 51}])
    def test_search_validation(self, client, body):
        assert client.post("/api/knowledge/search", json=body).status_code == 422

    def test_search_failure_502(self, client, monkeypatch):
        monkeypatch.setattr(knowledge, "search_knowledge", AsyncMock(side_effect=ConnectionError()))
        assert client.post("/api/knowledge/search", json={"query": "q"}).status_code == 502
        assert client.post("/api/knowledge/answer", json={"query": "q"}).status_code == 502

    def test_answer(self, client, monkeypatch):
        monkeypatch.setattr(knowledge, "search_knowledge", AsyncMock(return_value=[make_hit(1)]))
        answer = AsyncMock(return_value={"answer": "可以[1]"})
        monkeypatch.setattr(knowledge, "answer_from_hits", answer)
        assert client.post("/api/knowledge/answer", json={"query": "q"}).json() == {"answer": "可以[1]"}
        assert answer.await_args.args == ("q", [make_hit(1)])
        answer.side_effect = RuntimeError()
        assert client.post("/api/knowledge/answer", json={"query": "q"}).status_code == 502

    def test_cases_from_real_dataset(self, client):
        cases = client.get("/api/knowledge/cases").json()["cases"]
        assert cases and all("query" in case for case in cases)

    @pytest.fixture
    def report_path(self, tmp_path, monkeypatch):
        path = tmp_path / "reports" / "04.json"
        monkeypatch.setattr(knowledge, "REPORT_PATH", path)
        monkeypatch.setattr(knowledge, "load_cases", lambda: [{"query": "q"}])
        return path

    def test_report_missing_then_written_by_evaluate(self, client, report_path, monkeypatch):
        assert client.get("/api/rag-eval/report").json()["status"] == "not_evaluated"
        evaluate = AsyncMock(return_value={"status": "evaluated"})
        monkeypatch.setattr("app.core.evaluation.evaluate", evaluate)

        result = client.post("/api/knowledge/evaluate", json={"top_k": 3}).json()

        assert result["dataset"] == [{"query": "q"}]
        assert evaluate.await_args.kwargs == {"k": 3, "generate": False}
        assert json.loads(report_path.read_text(encoding="utf-8")) == result
        assert client.get("/rag-eval").json() == result
        assert client.get("/rag-eval", headers={"accept": "text/html"}).headers["content-type"].startswith("text/html")

    def test_evaluate_timeout_keeps_old_report(self, client, report_path, monkeypatch):
        monkeypatch.setattr("app.core.evaluation.evaluate", AsyncMock(side_effect=TimeoutError()))
        assert client.post("/api/knowledge/evaluate", json={}).status_code == 504
        assert not report_path.exists()

    async def test_evaluate_rejects_concurrent_run(self, client, report_path):
        async with knowledge.EVAL_LOCK:
            assert client.post("/api/knowledge/evaluate", json={}).status_code == 409


COST_REPORT = {
    "schema_version": 1,
    "meta": {"source": "s", "generated_at": "t", "scope": "provided_generations", "pricing_basis": "input_output_only"},
    "rows": [{
        "intent": "订单查询", "requests": 1, "generations": 2, "input_tokens": 10, "output_tokens": 5,
        "unknown_usage": 0, "unpriced": 0, "priced_subtotals": {"CNY": "0.01"}, "price_versions": ["v1"],
        "estimate_complete": True, "duration_samples": 2, "p95_generation_ms": 120.0,
    }],
    "summary": {"requests": 1, "generations": 2, "known_input_tokens": 10, "known_output_tokens": 5,
                "unknown_usage": 0, "unpriced": 0, "usage_complete": True, "estimate_complete": True},
}

CALIBRATION = {
    "status": "ok",
    "scan": [{"threshold": 0.5}],
    "scored": [{"score": 0.9, "answerable": True}, {"score": 0.7, "answerable": True}, {"score": 0.2, "answerable": False}],
    "recommended": {"threshold": 0.5},
}


def run(run_id, **extra):
    return {"id": run_id, "dataset_version": "v1", "case_ids": [1], "config_version": "c", "strategy": "s",
            "top_k": 5, **extra}


class TestObservability:
    @pytest.fixture(autouse=True)
    def paths(self, tmp_path, monkeypatch):
        monkeypatch.setattr(observability, "COST_REPORT_PATH", tmp_path / "cost.json")
        monkeypatch.setattr(observability, "CALIBRATION_PATH", tmp_path / "calibration.json")
        return tmp_path

    def test_cost_report_states(self, paths):
        assert observability.read_cost_report()["status"] == "missing"
        (paths / "cost.json").write_text(json.dumps(COST_REPORT), encoding="utf-8")
        report = observability.read_cost_report()
        assert (report["status"], report["present"], report["summary"]["generations"]) == ("ok", True, 2)
        (paths / "cost.json").write_text(json.dumps({**COST_REPORT, "rows": []}), encoding="utf-8")
        assert observability.read_cost_report()["hint"].startswith("报表已生成")

    @pytest.mark.parametrize(
        "patch",
        [{"schema_version": 2}, {"extra": 1}, {"summary": {**COST_REPORT["summary"], "requests": "1"}},
         {"summary": {**COST_REPORT["summary"], "requests": -1}}],
    )
    def test_cost_report_strict_schema(self, paths, patch):
        (paths / "cost.json").write_text(json.dumps({**COST_REPORT, **patch}), encoding="utf-8")
        assert observability.read_cost_report()["status"] == "error"

    def test_calibration(self, paths):
        assert observability.read_calibration()["status"] == "missing"
        (paths / "calibration.json").write_text(json.dumps(CALIBRATION), encoding="utf-8")
        report = observability.read_calibration()
        assert (report["status"], report["in_use"], report["in_sync"]) == ("ok", 0.5, True)
        assert report["distribution"]["answerable"] == {"n": 2, "min": 0.7, "p25": 0.7, "p50": 0.7, "p75": 0.9, "max": 0.9}

    @pytest.mark.parametrize(
        "content",
        ["not json", json.dumps({**CALIBRATION, "status": "draft"}),
         json.dumps({**CALIBRATION, "scored": [{"score": 1, "answerable": True}]})],
    )
    def test_calibration_errors(self, paths, content):
        (paths / "calibration.json").write_text(content, encoding="utf-8")
        assert observability.read_calibration()["status"] == "error"

    @pytest.mark.parametrize("recommended", [None, {}, []])
    def test_calibration_without_recommendation(self, paths, recommended):
        content = {k: v for k, v in CALIBRATION.items() if k != "recommended"}
        if recommended is not None:
            content["recommended"] = recommended
        (paths / "calibration.json").write_text(json.dumps(content), encoding="utf-8")
        assert observability.read_calibration()["status"] == "error"

    def test_distribution_empty(self):
        assert observability._distribution([])["p50"] is None

    async def test_trend(self, repo):
        repo.set("list_eval_runs", return_value=[run(3), run(2, top_k=10), run(1)])
        trend = await observability.read_trend()
        assert [r["id"] for r in trend["runs"]] == [3, 1]
        assert trend["omitted_incomparable"] == 1

    @pytest.mark.parametrize("setup,status", [({"return_value": []}, "missing"), ({"side_effect": RuntimeError()}, "error")])
    async def test_trend_states(self, repo, setup, status):
        repo.set("list_eval_runs", **setup)
        assert (await observability.read_trend())["status"] == status

    def test_overview_endpoint(self, client, repo):
        repo.set("list_eval_runs", return_value=[])
        body = client.get("/api/observability/overview").json()
        assert {key: block["status"] for key, block in body.items()} == {
            "cost": "missing", "trend": "missing", "calibration": "missing",
        }


class TestTopics:
    def test_catalog(self, client):
        classes = client.get("/api/topics/catalog").json()["classes"]
        assert [c["label"] for c in classes] == list(TOPIC_NAMES)

    def test_distribution(self, client, monkeypatch):
        monkeypatch.setattr(topics.topic_views, "distribution", AsyncMock(return_value={"total": 1}))
        assert client.get("/api/topics/distribution").json() == {"total": 1}
        monkeypatch.setattr(topics.topic_views, "distribution", AsyncMock(side_effect=SQLAlchemyError()))
        assert client.get("/api/topics/distribution").status_code == 503

    def test_questions(self, client, monkeypatch):
        label = TOPIC_NAMES[0]
        view = AsyncMock(return_value={"items": []})
        monkeypatch.setattr(topics.topic_views, "questions", view)
        assert client.get("/api/topics/questions", params={"label": label, "page": 2, "size": 5}).json() == {"items": []}
        assert view.await_args.kwargs == {"page": 2, "size": 5}
        assert client.get("/api/topics/questions", params={"label": "不存在"}).status_code == 400
        assert client.get("/api/topics/questions", params={"label": label, "size": 101}).status_code == 422
        view.side_effect = SQLAlchemyError()
        assert client.get("/api/topics/questions", params={"label": label}).status_code == 503


class TestJobs:
    @pytest.fixture
    def job(self, monkeypatch):
        name = next(iter(jobs.JOBS))
        monkeypatch.setattr(jobs, "status", lambda n, with_log=False: {"name": n, "log": with_log})
        return name

    def test_list(self, client, job):
        assert client.get("/api/jobs").json()["jobs"][0] == {"name": job, "log": False}

    def test_unknown_job_404(self, client, job):
        for method, path in [("get", "/api/jobs/nope"), ("post", "/api/jobs/nope"), ("post", "/api/jobs/nope/stop")]:
            assert getattr(client, method)(path).status_code == 404

    @pytest.mark.parametrize("error,status", [(None, 200), (RuntimeError("已在运行"), 409), (FileNotFoundError("x"), 500)])
    def test_start(self, client, job, monkeypatch, error, status):
        monkeypatch.setattr(jobs, "start", AsyncMock(side_effect=error))
        response = client.post(f"/api/jobs/{job}")
        assert response.status_code == status
        if status == 200:
            assert response.json() == {"name": job, "log": True}

    @pytest.mark.parametrize("error,status", [(None, 200), (RuntimeError("未运行"), 409)])
    def test_stop(self, client, job, monkeypatch, error, status):
        monkeypatch.setattr(jobs, "stop", AsyncMock(side_effect=error))
        assert client.post(f"/api/jobs/{job}/stop").status_code == status
        assert client.get(f"/api/jobs/{job}").json() == {"name": job, "log": True}

    def test_router_module(self):
        assert jobs_api.router.prefix == "/api/jobs"


class TestExtract:
    def test_returns_structured_ticket(self, client, monkeypatch):
        ticket = AfterSalesTicket(order_id="ORD-1", request_type=RequestType.REFUND, expected_solution="退款")
        model = patch_model(monkeypatch, extract, FakeStructuredModel(ticket))

        response = client.post("/api/extract", json={"text": "ORD-1 坏了要退款"})

        assert response.json() == {"order_id": "ORD-1", "request_type": "退款", "expected_solution": "退款"}
        assert model.schema is AfterSalesTicket
        assert [m.type for m in model.calls[0]] == ["system", "human"]

    def test_model_failure_502(self, client, monkeypatch):
        patch_model(monkeypatch, extract, FakeStructuredModel(error=RuntimeError()))
        assert client.post("/api/extract", json={"text": "x"}).status_code == 502

    def test_empty_text_422(self, client):
        assert client.post("/api/extract", json={"text": ""}).status_code == 422


class TestAdminOverview:
    @pytest.fixture
    def offline(self, repo, monkeypatch, tmp_path):
        """所有数据源都不可用时，每张卡片都应降级而不是报 500。"""
        repo.set("knowledge_stats", side_effect=RuntimeError())
        repo.set("topic_distribution", side_effect=RuntimeError())
        repo.set("list_eval_runs", return_value=[])
        monkeypatch.setattr(admin, "REPORT_PATH", tmp_path / "missing.json")
        monkeypatch.setattr(observability, "COST_REPORT_PATH", tmp_path / "cost.json")
        monkeypatch.setattr(observability, "CALIBRATION_PATH", tmp_path / "calibration.json")

        def session_local():
            raise RuntimeError("no mysql")

        monkeypatch.setattr(admin, "SessionLocal", session_local)
        monkeypatch.setattr(admin.acceptance, "overview", AsyncMock(side_effect=RuntimeError()))
        return repo

    def test_degrades_per_card(self, client, offline):
        modules = {m["key"]: m for m in client.get("/api/admin/overview").json()["modules"]}
        assert {k: m["status"] for k, m in modules.items()} == {
            "kb": "error", "rageval": "missing", "review": "error",
            "observability": "missing", "topics": "error", "classifier": "error",
        }

    @pytest.mark.parametrize(
        "stats,milvus,status",
        [
            ({"total": 0, "pending": 0, "done": 0, "key_clause": 0}, {"online": True, "count": 0}, "missing"),
            ({"total": 2, "pending": 0, "done": 2, "key_clause": 1}, {"online": False}, "attention"),
            ({"total": 2, "pending": 1, "done": 1, "key_clause": 1}, {"online": True, "count": 1}, "attention"),
            ({"total": 2, "pending": 0, "done": 2, "key_clause": 1}, {"online": True, "count": 2}, "ok"),
        ],
    )
    async def test_kb_card(self, repo, monkeypatch, stats, milvus, status):
        repo.set("knowledge_stats", return_value=stats)
        monkeypatch.setattr(admin.kb, "milvus_state", AsyncMock(return_value=milvus))
        assert (await admin._kb_card())["status"] == status

    @pytest.mark.parametrize(
        "content,status,headline",
        [
            ("{bad", "error", "读数失败"),
            (json.dumps({"status": "not_evaluated"}), "missing", "尚无完整评估结果"),
            (json.dumps({"status": "evaluated", "summary": {}}), "error", "读数失败"),
            (json.dumps({"status": "evaluated", "summary": {"vector": {"mrr": 0.5, "cases": 9},
                                                            "hybrid": {"mrr": 0.75}}}),
             "ok", "hybrid 的 MRR 最高：0.750"),
        ],
    )
    def test_rag_card(self, tmp_path, monkeypatch, content, status, headline):
        path = tmp_path / "04.json"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(admin, "REPORT_PATH", path)
        card = admin._rag_card()
        assert (card["status"], card["headline"]) == (status, headline)

    @pytest.mark.parametrize(
        "counts,status",
        [([], "missing"), ([("pending", 2)], "attention"), ([("approved", 3), ("rejected", 1)], "ok")],
    )
    async def test_review_card(self, monkeypatch, counts, status):
        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement):
                return type("Result", (), {"all": lambda self: counts})()

        monkeypatch.setattr(admin, "SessionLocal", Session)
        assert (await admin._review_card())["status"] == status

    @pytest.mark.parametrize("total,status", [(0, "missing"), (4, "ok")])
    async def test_topics_card(self, repo, total, status):
        repo.set("topic_distribution", return_value={"total": total, "classes": [{"count": total}, {"count": 0}]})
        card = await admin._topics_card()
        assert card["status"] == status
        assert card["metrics"][1]["value"] == f"{1 if total else 0}/2"

    @pytest.mark.parametrize(
        "result,status",
        [
            ({"passed": 9, "total": 9, "all_pass": True, "classifier": {"online": True}, "blocks": []}, "ok"),
            ({"passed": 7, "total": 9, "all_pass": False, "classifier": {"online": False},
              "blocks": [{"status": "fail"}, {"status": "missing"}]}, "attention"),
            ({"passed": 8, "total": 9, "all_pass": False, "classifier": {"online": False},
              "blocks": [{"status": "missing"}]}, "missing"),
        ],
    )
    async def test_classifier_card(self, monkeypatch, result, status):
        monkeypatch.setattr(admin.acceptance, "overview", AsyncMock(return_value=result))
        assert (await admin._classifier_card())["status"] == status

    @pytest.mark.parametrize(
        "statuses,status",
        [(("ok", "ok", "ok"), "ok"), (("ok", "missing", "ok"), "attention"), (("missing",) * 3, "missing")],
    )
    async def test_observability_card(self, monkeypatch, statuses, status):
        cost, trend, calibration = ({"status": s} for s in statuses)
        trend["runs"] = [1, 2]
        monkeypatch.setattr(admin.observability, "overview",
                            AsyncMock(return_value={"cost": cost, "trend": trend, "calibration": calibration}))
        assert (await admin._observability_card())["status"] == status
