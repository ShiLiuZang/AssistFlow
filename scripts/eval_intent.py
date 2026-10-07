"""
意图分类评估脚本
读取标准样例与预测结果，计算准确率、精确率、召回率和F1分数
用于验证意图识别模块的性能
"""
import argparse
import json
import sys
from pathlib import Path

from app.core.intent_evaluation import evaluate_intent


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="评估意图分类结果")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("data/eval/intent.json"),
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    predictions = json.loads(
        args.predictions.read_text(encoding="utf-8")
    )

    report = evaluate_intent(cases, predictions)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
