"""校准与固定集评测的可比较口径。"""

import math


def calibrate(rows: list[dict], thresholds: list[float]) -> dict:
    if not rows or any(row.get("split") != "calibration" for row in rows):
        raise ValueError("阈值只允许用 calibration 集选择")
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("校准样本 ID 重复")
    for row in rows:
        score = row.get("score")
        if (
            type(row.get("answerable")) is not bool
            or isinstance(score, bool)
            or not isinstance(score, (float, int))
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError("校准标签或分数无效")
    positive = [row for row in rows if row["answerable"]]
    negative = [row for row in rows if not row["answerable"]]
    if not positive or not negative or not thresholds:
        raise ValueError("校准集需要可答、应拒两类样本和阈值")

    scan = []
    for threshold in thresholds:
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("阈值无效")
        pass_rate = sum(row["score"] >= threshold for row in positive) / len(positive)
        leak_rate = sum(row["score"] >= threshold for row in negative) / len(negative)
        scan.append({
            "threshold": threshold,
            "pass_rate": pass_rate,
            "leak_rate": leak_rate,
            "youden_j": pass_rate - leak_rate,
        })
    recommended = max(scan, key=lambda row: (row["youden_j"], row["threshold"]))
    return {"scan": scan, "recommended": recommended}


def comparable(before: dict, after: dict) -> bool:
    return all(
        before[key] == after[key]
        for key in ("dataset_version", "case_ids", "config_version", "strategy", "top_k")
    )
