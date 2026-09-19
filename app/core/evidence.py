"""Ch04：证据编号与引用校验。"""
import re
REFUSAL = "现有知识库没有足够证据确认这个问题，请联系人工客服。"
def number_evidence(hits: list[dict]) -> list[dict]:
    """为本次检索结果分配引用编号，保留原始字段。"""
    return [
        {**hit, "n": index + 1}
        for index, hit in enumerate(hits)
    ]
def cited_numbers(answer: str) -> set[int]:
    """提取回答中的引用编号。"""
    return {
        int(number)
        for number in re.findall(r"\[(\d+)\]", answer)
    }


def citations_exist(answer: str, citations: list[dict]) -> bool:
    """检查回答中的每个引用编号是否存在。"""
    if not answer.strip():
        return False

    cited = cited_numbers(answer)
    available = {
        item["n"]
        for item in citations
    }

    return bool(cited) and cited.issubset(available)

def quotes_match(
    quotes: list[dict],
    citations: list[dict],
) -> bool:
    """检查每条引用原文是否属于对应证据。"""
    by_number = {
        item["n"]: item
        for item in citations
    }

    if not quotes:
        return False

    for quote in quotes:
        number = quote.get("n")
        text = quote.get("text", "").strip()

        if number not in by_number or not text:
            return False

        source = by_number[number].get("answer", "")
        if text not in source:
            return False

    return True

def model_codes(text: str) -> set[str]:
    """提取文本中的商品型号。"""
    return set(
        re.findall(r"MH-[A-Z0-9]+", text.upper())
    )


def answer_is_grounded(
    answer: str,
    quotes: list[dict],
    citations: list[dict],
) -> bool:
    """检查回答是否有合法引用、原文和型号依据。"""
    if not citations_exist(answer, citations):
        return False

    if not quotes_match(quotes, citations):
        return False

    cited = cited_numbers(answer)
    quoted = {
        quote["n"]
        for quote in quotes
    }

    if not cited.issubset(quoted):
        return False

    by_number = {
        item["n"]: item
        for item in citations
    }

    source_text = "\n".join(
        by_number[number].get("answer", "")
        for number in cited
    )

    return model_codes(answer).issubset(
        model_codes(source_text)
    )
def refusal_result() -> dict:
    """生成统一的证据不足结果。"""
    return {
        "answer": REFUSAL,
        "refused": True,
        "citations": [],
    }


def grounded_result(
    answer: str,
    quotes: list[dict],
    citations: list[dict],
) -> dict:
    """验证通过返回回答，否则返回拒答。"""
    if not answer_is_grounded(answer, quotes, citations):
        return refusal_result()

    return {
        "answer": answer,
        "refused": False,
        "citations": citations,
    }
