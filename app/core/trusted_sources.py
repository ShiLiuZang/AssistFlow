"""核准答案只能来自项目内受信材料的连续原文。"""

from hashlib import sha256
import re

from app.kb.sources import KB_DIR, SOURCE_TYPES


PERSONAL_DATA = re.compile(
    r"ORD-\w+|\b1[3-9]\d{9}\b|[\w.+-]+@[\w.-]+",
    re.IGNORECASE,
)


def validate_review_source(question: str, answer: str, source_ref: str) -> str:
    """返回材料 SHA-256；拒绝未知来源、个人标识和无依据答案。"""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("标准问题不能为空")
    if PERSONAL_DATA.search(question):
        raise ValueError("标准问题含订单号或联系方式，请先脱敏")
    if not isinstance(source_ref, str) or source_ref not in SOURCE_TYPES:
        raise ValueError("来源不在材料白名单中")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("核准答案不能为空")

    source = (KB_DIR / source_ref).read_text(encoding="utf-8")
    if answer.strip() not in source:
        raise ValueError("核准答案必须是可信材料中的连续原文")
    return sha256(source.encode("utf-8")).hexdigest()
