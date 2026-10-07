"""
测试意图分类评估功能
覆盖准确率计算、混淆矩阵统计、错例收集和固定数据集验证
"""
import pytest
import json
import sys
from pathlib import Path

from app.core.intent import INTENT_PROMPT, Intent
from app.core.intent_evaluation import evaluate_intent
from scripts.eval_intent import main


def test_confusion_counts_repeated_errors_and_correct_pairs():
    """测试混淆矩阵：统计重复错误和正确配对"""
    cases = [
        {"query": "转人工", "expected": "人工"},
        {"query": "找客服本人", "expected": "人工"},
        {"query": "你好", "expected": "闲聊"},
    ]
    predictions = [
        {"intent": "投诉", "confidence": 0.99},
        {"intent": "投诉", "confidence": 0.8},
        {"intent": "闲聊", "confidence": 0.1},
    ]
    result = evaluate_intent(cases, predictions)
    assert result["count"] == 3
    assert result["accuracy"] == pytest.approx(1 / 3)
    assert result["confusion"] == [
        {"expected": "人工", "predicted": "投诉", "count": 2},
        {"expected": "闲聊", "predicted": "闲聊", "count": 1},
    ]
    assert result["errors"] == [
        {"query": "转人工", "expected": "人工", "predicted": "投诉"},
        {"query": "找客服本人", "expected": "人工", "predicted": "投诉"},
    ]
    changed = [{**row, "confidence": 1 - row["confidence"]} for row in predictions]
    assert evaluate_intent(cases, changed) == result


@pytest.mark.parametrize("prediction, accuracy, errors", [
    ("订单", 1.0, []),
    ("物流", 0.0, [{"query": "金额", "expected": "订单", "predicted": "物流"}]),
])
def test_all_correct_or_all_wrong(prediction, accuracy, errors):
    """测试全对或全错场景"""
    result = evaluate_intent(
        [{"query": "金额", "expected": "订单"}],
        [{"intent": prediction, "confidence": 0.9}],
    )
    assert result["accuracy"] == accuracy
    assert result["errors"] == errors


@pytest.mark.parametrize("cases, predictions", [
    ([], []),
    ([{"expected": "订单"}], []),
    ([{"expected": "未知"}], [{"intent": "订单", "confidence": 0.9}]),
    ([{"expected": "订单"}], [{"intent": "未知", "confidence": 0.9}]),
    ([{"expected": "订单"}], [{"intent": "订单", "confidence": "0.9"}]),
])
def test_invalid_evaluation_inputs(cases, predictions):
    """测试非法输入拒绝：空数据、未知标签、类型错误"""
    with pytest.raises(ValueError):
        evaluate_intent(cases, predictions)


def test_eval_intent_command_prints_report(monkeypatch, capsys):
    """测试评估命令：读取预测文件并输出报告"""
    monkeypatch.setattr(sys, "argv", [
        "eval_intent",
        "--predictions", "tests/data/intent_predictions.json",
    ])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["count"] == 9
    assert report["accuracy"] == pytest.approx(8 / 9)
    assert report["errors"] == [{
        "query": "别让我再和机器人聊了，请帮我接人工客服",
        "expected": "人工",
        "predicted": "投诉",
    }]


def test_seed_cases_cover_labels_and_stay_out_of_prompt():
    """测试种子数据集：覆盖所有标签且不泄漏到prompt"""
    cases = json.loads(
        Path("data/eval/intent.json").read_text(encoding="utf-8")
    )
    assert {case["expected"] for case in cases} == {intent.value for intent in Intent}
    assert all(case["query"] not in INTENT_PROMPT for case in cases)
