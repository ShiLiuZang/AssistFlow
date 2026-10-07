"""
测试检索评估框架
覆盖检索指标计算、生成评估、拒答准确率和固定数据集验证
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.conftest import ADMIN_HEADERS

from app.core import evaluation as ev
from app.api import knowledge
from scripts.eval_retrieval import validate_cases, ROOT


CASES = [
    {"id": "answer", "query": "问题", "groups": [["条件"], ["运费"]],
     "should_refuse": False, "expected_terms": ["条件", "运费"]},
    {"id": "refuse", "query": "超出知识范围", "groups": [],
     "should_refuse": True, "expected_terms": []},
]


def test_metrics_use_groups_and_cutoff():
    """测试检索指标计算：基于分组和截断点计算召回率和MRR"""
    hits = [{"section_path": p} for p in ["无关", "条件", "替代条件", "运费"]]
    groups = [["条件", "替代条件"], ["运费"]]
    assert ev.retrieval_metrics(hits, groups, 3) == {"recall": .5, "rr": .5}
    assert ev.retrieval_metrics([], groups, 3) == {"recall": 0, "rr": 0}
    assert ev.retrieval_metrics([], [], 3) == {"recall": None, "rr": None}


def test_failures_keep_denominators():
    """测试失败计数：连接失败时保留分母，不跳过生成"""
    with patch.object(ev, "search_knowledge", AsyncMock(side_effect=ConnectionError)), \
         patch.object(ev, "answer_from_hits", AsyncMock()) as generate:
        report = asyncio.run(ev.evaluate(CASES))
    assert len(report["details"]) == 8
    generate.assert_not_awaited()
    for summary in report["summary"].values():
        assert summary["cases"] == 2
        assert summary["answerable_cases"] == 1
        assert summary["failures"] == 2
        assert summary["recall_at_k"] == summary["mrr"] == 0
        assert summary["refusal_accuracy"] == summary["keyword_coverage"] == 0


def test_generation_and_fixed_inputs():
    """测试生成评估：使用固定K值和参数，验证拒答和关键词覆盖"""
    async def answer(query, hits):
        return {"answer": "条件和运费", "refused": query == "超出知识范围"}
    hits = [{"section_path": "条件"}, {"section_path": "运费"}]
    with patch.object(ev, "search_knowledge", AsyncMock(return_value=hits)) as search, \
         patch.object(ev, "answer_from_hits", AsyncMock(side_effect=answer)):
        report = asyncio.run(ev.evaluate(CASES, k=2))
    for call in search.await_args_list:
        assert call.kwargs == {"top_k": 2, "rewrite": False, "split": False}
    for summary in report["summary"].values():
        assert summary["recall_at_k"] == summary["mrr"] == 1
        assert summary["refusal_accuracy"] == summary["keyword_coverage"] == 1


def test_skip_generation():
    """测试跳过生成：generate=False时不调用生成模块"""
    with patch.object(ev, "search_knowledge", AsyncMock(return_value=[])), \
         patch.object(ev, "answer_from_hits", AsyncMock()) as generate:
        report = asyncio.run(ev.evaluate(CASES, generate=False))
    generate.assert_not_awaited()
    assert all("refusal_accuracy" not in s for s in report["summary"].values())


def test_report_missing_and_present(tmp_path):
    """测试评估报告接口：未评估时返回not_evaluated，有报告时返回内容"""
    app = FastAPI()
    app.include_router(knowledge.router)
    client = TestClient(app, headers=ADMIN_HEADERS)
    path = tmp_path / "report.json"
    with patch.object(knowledge, "REPORT_PATH", path):
        assert client.get("/api/rag-eval/report").json()["status"] == "not_evaluated"
        path.write_text('{"status":"evaluated"}', encoding="utf-8")
        assert client.get("/api/rag-eval/report").json()["status"] == "evaluated"


def test_fixed_dataset_sources():
    """测试固定数据集：验证数据格式和来源完整性"""
    cases = [json.loads(line) for line in
             (ROOT / "tests/data/eval_retrieval.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    validate_cases(cases)
