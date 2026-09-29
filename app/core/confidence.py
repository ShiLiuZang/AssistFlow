# 模块：证据置信度评估
# 对检索召回的知识块进行质量评估，决定是否允许模型生成答案
# 综合考虑重排分数、有效召回数、分数差距、关键条款命中等多维信号
# 核心职责：低质量证据时拒答，避免模型胡编答案

from copy import deepcopy
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Decision:
    """证据闸门决策结果"""
    allow: bool  # 是否允许生成答案
    source: str | None  # 拒答来源（如"retrieval_low_conf"、"self_check"）
    reason: str  # 决策原因（如"no_evidence"、"insufficient_evidence"、"passed"）
    confidence: dict  # 置信度计算详情
    snapshot: list[dict]  # 证据快照（前3条）

# 关键条款识别词：出现这些词的知识块权重更高
KEY_TERMS = ("退款", "退货", "运费", "保修", "期限")
def ranked_hits(hits: list[dict]) -> list[dict]:
    """
    校验精排分数，按知识块ID去重，再按分数降序排列

    参数:
        hits: 检索召回的知识块列表

    返回:
        去重并排序后的知识块列表

    处理逻辑:
        1. 检查每个知识块是否有有效的ID和精排分数
        2. 同一ID出现多次时保留分数最高的那条
        3. 按精排分数降序排列

    异常:
        ValueError: 缺少ID、分数不合法（非0-1之间的有限数值）

    设计说明:
        rerank_score是重排序模型给出的相关性分数，取值[0,1]
        混合检索可能返回同一知识块的多个变体，去重确保不重复引用
    """
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
    """
    计算证据整体置信度

    参数:
        hits: 检索召回的知识块列表

    返回:
        包含置信度分数和各维度信号的字典

    评估维度（权重分配）:
        - top1_score (50%): 最高分知识块的相关性
        - valid_count (20%): 分数>=0.3的知识块数量（最多计3条）
        - margin (20%): 第1名与第2名的分数差距
        - key_clause_hit (10%): 前3条是否命中关键条款

    设计说明:
        top1高说明有相关知识；valid_count多说明召回面宽；
        margin大说明第1名显著领先；key_clause_hit说明涉及核心政策
        四维信号综合判断证据质量，避免单一指标误判
    """
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
    """
    提取证据快照（前3条）

    参数:
        hits: 检索召回的知识块列表

    返回:
        前3条知识块的关键字段列表

    提取字段:
        - id: 知识块ID
        - question: 问法
        - answer: 答案正文
        - section_path: 章节路径
        - rerank_score: 精排分数

    设计说明:
        证据快照用于日志溯源和低置信度问题归档
        只保留关键字段避免日志膨胀，前3条足够还原决策现场
    """
    ranked = ranked_hits(hits)

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
    """
    证据质量闸门：决定是否允许生成答案

    参数:
        question: 用户问题
        hits: 检索召回的知识块列表
        threshold: 置信度阈值（0-1之间）
        check: 充分性检查函数（异步，接收问题和证据，返回{"useful": bool}）
        evidence: 过滤后的有效证据列表

    返回:
        Decision对象，包含决策结果、拒答原因、置信度、证据快照

    闸门流程（任一条件不满足则拒答）:
        1. 检查是否有证据快照（hits为空时拒答）
        2. 检查是否有有效证据（过滤后为空时拒答）
        3. 检查置信度是否达标
        4. 调用充分性检查，询问模型证据是否足以回答

    设计说明:
        先检查量化指标（置信度），再调用模型判断质量
        顺序不能反：置信度低时无需浪费模型调用
        充分性检查失败或超时时拒答，确保可靠性优先
    """
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
