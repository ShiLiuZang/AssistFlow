"""用独立校准集的真实检索分数选择阈值；不会自动修改在线配置。"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.core.confidence import compute_evidence_confidence
from app.core.flywheel_evaluation import calibrate
from app.core.retrieval import search_knowledge


async def run(dataset: Path, output: Path, version: str) -> dict:
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(row.get("split") != "calibration" for row in rows):
        raise ValueError("输入文件只能包含 calibration 样本")
    scored = []
    for row in rows:
        if type(row.get("answerable")) is not bool or not row.get("query"):
            raise ValueError("校准样本缺少 query 或 answerable")
        hits = await search_knowledge(row["query"], "hybrid_rerank", top_k=5, rewrite=False, split=False)
        scored.append({
            "id": row["id"],
            "split": "calibration",
            "answerable": row["answerable"],
            "score": compute_evidence_confidence(hits)["score"],
        })
    result = calibrate(scored, [round(i / 100, 2) for i in range(5, 96)])
    report = {
        **result,
        "status": "ok",
        "dataset_version": version,
        "case_ids": [row["id"] for row in rows],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "in_use": settings.evidence_min_confidence,
        "in_sync": result["recommended"]["threshold"] == settings.evidence_min_confidence,
        "weights": {"top1": 0.5, "valid_count": 0.2, "margin": 0.2, "key_clause": 0.1},
        "scored": scored,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/09/reports/calibration.json"))
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.dataset, args.output, args.dataset_version))["recommended"], ensure_ascii=False))
