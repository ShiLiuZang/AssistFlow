"""/api/acceptance：分类器九项验收（产物目录为临时目录，:8110 分类服务为 httpx 替身）。"""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api import acceptance
from app.core.taxonomy import TOPIC_NAMES

A, B = TOPIC_NAMES[0], TOPIC_NAMES[1]


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def finetune(tmp_path, monkeypatch):
    root = tmp_path / "finetune"
    for name, path in {"FINETUNE_DIR": root, "REPORTS": root / "reports", "DATASET": root / "dataset",
                       "MODEL": root / "model", "ONNX": root / "onnx"}.items():
        monkeypatch.setattr(acceptance, name, path)
    monkeypatch.setattr(acceptance.jobs, "status_all", lambda: [])
    monkeypatch.setattr(acceptance.topic_views, "distribution",
                        AsyncMock(return_value={"total": 3, "classes": [{"count": 3}, {"count": 0}]}))
    return root


@pytest.fixture
def classifier(monkeypatch):
    """替换 httpx.AsyncClient，让请求落到 MockTransport；state 控制返回。"""
    state = {"health": {"ok": True}, "result": {"labels": [A], "scores": {A: 0.9, B: 0.2}}, "fail": False}
    requests = []

    def handler(request):
        requests.append(request)
        if state["fail"]:
            raise httpx.ConnectError("refused")
        if request.url.path == "/healthz":
            return httpx.Response(200, json=state["health"])
        return httpx.Response(200, json={"results": [state["result"]]})

    real = httpx.AsyncClient
    monkeypatch.setattr(acceptance.httpx, "AsyncClient",
                        lambda timeout: real(transport=httpx.MockTransport(handler), timeout=timeout))
    state["requests"] = requests
    return state


def complete_artifacts(root):
    for name in ("corpus_raw.jsonl", "corpus_clean.jsonl", "corpus_labeled.jsonl"):
        write_jsonl(root / name, [{"text": "t", "origin": "real"}, {"text": "u"}])
    write_jsonl(root / "dataset" / "train.jsonl", [{"text": "a", "labels": [A, B]}, {"text": "b", "labels": [A]}])
    write_jsonl(root / "dataset" / "val.jsonl", [{"text": "c", "labels": [B]}])
    write_jsonl(root / "dataset" / "test.jsonl", [{"text": "d", "labels": [A], "origin": "real"}])
    (root / "model").mkdir()
    (root / "model" / "model.safetensors").write_bytes(b"x" * 2 * 1024 * 1024)
    (root / "model" / "tokenizer.json").write_text("{}")
    write_json(root / "model" / "threshold.json", {"threshold": 0.5})
    (root / "onnx").mkdir()
    for name in ("model.onnx", "tokenizer.json", "threshold.json"):
        (root / "onnx" / name).write_text("{}")
    reports = root / "reports"
    write_json(reports / "golden_report.json", {"passed": True, "rate": 1.0, "pass_line": 0.9, "hits": 9, "total": 9})
    write_json(reports / "export_report.json", {"passed": True, "checked": 10, "mismatch": 0})
    write_json(reports / "threshold_scan.json", {"consistent": True, "best_threshold": 0.5, "best_micro_f1": 0.95,
                                                 "in_use_threshold": 0.5})
    write_json(reports / "eval_report.json", {
        "red_line_passed": True, "micro": {"f1": 0.95}, "macro": {"f1": 0.9}, "test_size": 1,
        "real_subset": {"size": 1}, "total_cells": 17, "total_fp": 1, "total_fn": 1,
        "ran_at": "2026-01-01", "threshold": 0.5,
        "errors": [{"kind": "错位", "missed": [A], "extra": [B], "matrix_entries": 2}],
    })
    write_json(reports / "classify_run.json", {"status": "done", "written": 3})


class TestHelpers:
    def test_stat(self, tmp_path):
        assert acceptance._stat(tmp_path / "none")["present"] is False
        path = tmp_path / "a.jsonl"
        path.write_text('{"a":1}\n\n{"a":2}\n', encoding="utf-8")
        stat = acceptance._stat(path)
        assert (stat["present"], stat["lines"], stat["bytes"]) == (True, 2, path.stat().st_size)
        (tmp_path / "b.bin").write_bytes(b"x")
        assert "lines" not in acceptance._stat(tmp_path / "b.bin")

    def test_load_report(self, finetune):
        assert acceptance._load_report("x.json", "make-x")["hint"].endswith("make-x")
        (finetune / "reports").mkdir(parents=True)
        (finetune / "reports" / "bad.json").write_text("{", encoding="utf-8")
        assert acceptance._load_report("bad.json", "m")["hint"].startswith("产物解析失败")
        write_json(finetune / "reports" / "ok.json", {"v": 1})
        assert acceptance._load_report("ok.json", "m") == {"v": 1, "present": True, "make": "m"}

    def test_jsonl_and_origins(self, tmp_path):
        assert acceptance._read_jsonl(tmp_path / "none.jsonl") == []
        write_jsonl(tmp_path / "x.jsonl", [{"origin": "real"}, {"origin": "real"}, {"origin": ""}, {}])
        assert acceptance._origin_counts(acceptance._read_jsonl(tmp_path / "x.jsonl")) == {"real": 2, "unmarked": 2}

    def test_split_stats_detects_leaks(self, finetune):
        write_jsonl(finetune / "dataset" / "train.jsonl", [{"text": "same", "labels": [A, B]}])
        write_jsonl(finetune / "dataset" / "test.jsonl", [{"text": "same", "labels": ["不存在的类"]}])
        stats = acceptance._split_stats()
        assert stats["leaks"] == {"train_val": 0, "train_test": 1, "val_test": 0}
        assert stats["clean"] is False
        assert stats["splits"]["train"]["multi_label"] == 1
        assert stats["splits"]["test"]["counts"][A] == 0


class TestOverview:
    def test_everything_missing(self, client, finetune, monkeypatch):
        monkeypatch.setattr(acceptance.topic_views, "distribution", AsyncMock(side_effect=RuntimeError()))
        body = client.get("/api/acceptance/overview").json()
        assert (body["passed"], body["total"], body["all_pass"]) == (0, 9, False)
        assert {b["status"] for b in body["blocks"]} == {"missing"}
        assert body["classifier"] == {"online": False, "detail": "当前项目尚无 ONNX 分类器产物"}
        assert body["blocks"][-1]["note"].startswith("库里读数失败")

    def test_all_pass(self, client, finetune, classifier):
        complete_artifacts(finetune)
        body = client.get("/api/acceptance/overview").json()
        assert [b["status"] for b in body["blocks"]] == ["pass"] * 9
        assert body["all_pass"] is True
        assert body["classifier"] == {"online": True, "detail": {"ok": True}}
        headlines = {b["key"]: b["headline"] for b in body["blocks"]}
        assert headlines["data"].endswith("2/1/1 训练/验证/测试")
        assert headlines["train"] == "权重 2MB · tokenizer · threshold 0.5"
        assert headlines["classify"] == "问题池上次归类写入 3 条"

    def test_classifier_offline_fails_export_gate(self, client, finetune, classifier):
        complete_artifacts(finetune)
        classifier["fail"] = True
        blocks = {b["key"]: b["status"] for b in client.get("/api/acceptance/overview").json()["blocks"]}
        assert blocks["export"] == "fail"

    def test_history_source_uses_history_report(self, client, finetune, classifier, monkeypatch):
        complete_artifacts(finetune)
        monkeypatch.setattr(acceptance.topic_views, "distribution", AsyncMock(return_value={
            "total": 0, "classes": [], "source": "conversation_history"}))
        write_json(finetune / "reports" / "history_classify_run.json",
                   {"status": "empty", "source": "conversation_history"})
        block = client.get("/api/acceptance/overview").json()["blocks"][-1]
        assert block["headline"] == "历史会话已全部归类，本次写入 0 条(幂等)"


class TestDetails:
    def test_eval_detail_hides_errors(self, client, finetune, classifier):
        complete_artifacts(finetune)
        body = client.get("/api/acceptance/eval").json()
        assert "errors" not in body["eval"]
        assert body["threshold_in_use"] == 0.5

    def test_data_detail(self, client, finetune):
        complete_artifacts(finetune)
        body = client.get("/api/acceptance/data").json()
        assert [item["stage"] for item in body["lineage"]] == ["取数", "脱敏去重", "预标 + 模拟补足"]
        assert body["corpus_origins"] == {"real": 1, "unmarked": 1}
        assert body["model"]["trio_ok"] is True
        assert len(body["onnx"]["files"]) == 3

    def test_errors_detail(self, client, finetune):
        assert client.get("/api/acceptance/errors").json()["errors"] == []
        complete_artifacts(finetune)
        body = client.get("/api/acceptance/errors").json()
        assert body["kinds"] == {"错位": 1}
        assert body["pairs"] == [{"missed": A, "grabbed": B, "count": 1, "severity": acceptance.SEVERITY.get(A)}]
        assert (body["matrix_entries"], body["total_fp"]) == (2, 1)

    def test_service(self, client, finetune):
        assert client.get("/api/acceptance/service").json() == {
            "online": False, "detail": "当前项目尚无 ONNX 分类器产物", "threshold": None, "onnx_present": False,
        }


class TestClassify:
    def test_empty_text(self, client, finetune):
        assert client.post("/api/acceptance/classify", json={"text": "  "}).status_code == 400

    def test_without_onnx(self, client, finetune):
        assert client.post("/api/acceptance/classify", json={"text": "退货"}).status_code == 503

    def test_scores_sorted_with_fallback_flag(self, client, finetune, classifier):
        complete_artifacts(finetune)
        body = client.post("/api/acceptance/classify", json={"text": " 退货 "}).json()
        assert body["text"] == "退货"
        assert [s["label"] for s in body["scores"]] == [A, B]
        assert [s["hit"] for s in body["scores"]] == [True, False]
        assert body["fallback"] is False
        assert json.loads(classifier["requests"][-1].content) == {"texts": ["退货"]}

        classifier["result"] = {"labels": [], "scores": {A: 0.3}}
        assert client.post("/api/acceptance/classify", json={"text": "x"}).json()["fallback"] is True

    def test_service_down(self, client, finetune, classifier):
        complete_artifacts(finetune)
        classifier["fail"] = True
        assert client.post("/api/acceptance/classify", json={"text": "x"}).status_code == 502
