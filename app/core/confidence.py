from copy import deepcopy
from dataclasses import dataclass
import math
@dataclass(frozen=True)
class Decision:
    allow: bool
    source: str | None
    reason: str
    confidence: dict
    snapshot: list[dict]
KEY_TERMS = ("退款", "退货", "运费", "保修", "期限")
def ranked_hits(hits: list[dict]) -> list[dict]:
    """校验精排分数，按知识块 ID 去重，再按分数降序排列。"""
    unique: dict[int | str, dict] = {}

    for hit in hits:
        if not isinstance(hit, dict):
            raise ValueError("证据必须是字典")

        hit_id = hit.get("id")
        if (
            isinstance(hit_id, bool)
            or not isinstance(hit_id, (int, str))
            or isinstance(hit_id, str) and not hit_id.strip()
        ):
            raise ValueError("证据缺少有效的知识块 ID")

        score = hit.get("rerank_score")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError("精排分数必须是 0 到 1 之间的有限数值")

        previous = unique.get(hit_id)
        if previous is None or score > previous["rerank_score"]:
            unique[hit_id] = deepcopy(hit)

    return sorted(
        unique.values(),
        key=lambda hit: (-hit["rerank_score"], str(hit["id"])),
    )
def compute_evidence_confidence(hits: list[dict]) -> dict:
    ranked = ranked_hits(hits)
    scores = [hit["rerank_score"] for hit in ranked]

    top1 = scores[0] if scores else 0.0
    margin = top1 - scores[1] if len(scores) > 1 else top1
    valid_count = sum(score >= 0.3 for score in scores)

    key_clause_hit = False
    for hit in ranked[:3]:
        question = hit.get("question", "")
        answer = hit.get("answer", "")

        if not isinstance(question, str) or not isinstance(answer, str):
            raise ValueError("证据的问题和答案必须是字符串")

        text = question + "\n" + answer
        if any(term in text for term in KEY_TERMS):
            key_clause_hit = True

    score = (
        0.5 * top1
        + 0.2 * min(valid_count, 3) / 3
        + 0.2 * margin
        + 0.1 * int(key_clause_hit)
    )

    return {
        "score": round(score, 4),
        "signals": {
            "top1_score": top1,
            "valid_count": valid_count,
            "margin": margin,
            "key_clause_hit": key_clause_hit,
        },
    }
def snapshot_from_hits(hits: list[dict]) -> list[dict]:
    ranked= ranked_hits(hits)

    fields = (
        "id",
        "question",
        "answer",
        "section_path",
        "rerank_score",
    )

    result = []
    for hit in ranked[:3]:
        selected = {}
        for field in fields:
            selected[field] = hit.get(field)
        result.append(selected)
    return result
async def evidence_gate(
    question: str,
    hits: list[dict],
    threshold: float,
    check,
    *,
    evidence: list[dict],
) -> Decision:
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or not 0 <= threshold <= 1
    ):
        raise ValueError("证据阈值必须是 0 到 1 之间的有限数值")

    confidence = compute_evidence_confidence(hits)
    snapshot = snapshot_from_hits(hits)

    if not snapshot:
        return Decision(
            allow=False,
            source="retrieval_low_conf",
            reason="no_evidence",
            confidence=confidence,
            snapshot=snapshot,
        )
    if not evidence:
        return Decision(
            allow=False,
            source="retrieval_low_conf",
            reason="no_eligible_evidence",
            confidence=confidence,
            snapshot=snapshot,
        )
    if confidence["score"] < threshold:
        return Decision(
            allow=False,
            source="retrieval_low_conf",
            reason="score_below_threshold",
            confidence=confidence,
            snapshot=snapshot,
        )

    try:
        result = await check(question, deepcopy(evidence))

        if (
            not isinstance(result, dict)
            or type(result.get("useful")) is not bool
        ):
            raise ValueError("充分性检查必须返回布尔类型的 useful")
    except Exception:
        return Decision(
            allow=False,
            source="self_check",
            reason="check_error",
            confidence=confidence,
            snapshot=snapshot,
        )

    if not result["useful"]:
        return Decision(
            allow=False,
            source="self_check",
            reason="insufficient_evidence",
            confidence=confidence,
            snapshot=snapshot,
        )

    return Decision(
        allow=True,
        source=None,
        reason="passed",
        confidence=confidence,
        snapshot=snapshot,
    )
