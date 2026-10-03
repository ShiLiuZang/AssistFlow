"""在固定 holdout 集上真实检索与生成，并把结果保存到 eval_runs。"""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.evaluation import evaluate
from app.db import trace_repo


async def run(dataset: Path, dataset_version: str, config_version: str, kb_revision: str, k: int) -> int:
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases or any(case.get("split") != "holdout" for case in cases):
        raise ValueError("最终复评只接受 holdout 集")
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)) or not all(ids):
        raise ValueError("评测样本 ID 缺失或重复")
    if not all((dataset_version, config_version, kb_revision)) or k < 1:
        raise ValueError("版本和 K 必填")
    for case in cases:
        if bool(case.get("groups")) == case.get("should_refuse"):
            raise ValueError("证据组与拒答标签不一致")

    report = await evaluate(cases, k=k, generate=True)
    strategy = "hybrid_rerank"
    details = [
        {
            key: value for key, value in row.items()
            if key != "hits"
        }
        for row in report["details"] if row["strategy"] == strategy
    ]
    summary = report["summary"][strategy]
    metrics = {
        "recall_at_k": summary["recall_at_k"],
        "mrr": summary["mrr"],
        "refusal_accuracy": summary["refusal_accuracy"],
        "keyword_coverage": summary["keyword_coverage"],
        "faithfulness": None,
        "judged_cases": 0,
        "failures": summary["failures"],
        "cases": len(cases),
    }
    return await trace_repo.save_eval_run({
        "dataset_version": dataset_version,
        "case_ids": ids,
        "config_version": config_version,
        "kb_revision": kb_revision,
        "strategy": strategy,
        "top_k": k,
        "triggered_by": "manual-cli",
        "status": "partial" if metrics["failures"] else "completed",
        "metrics": metrics,
        "details": details,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--config-version", required=True)
    parser.add_argument("--kb-revision", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    print(asyncio.run(run(args.dataset, args.dataset_version, args.config_version, args.kb_revision, args.top_k)))
