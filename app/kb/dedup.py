# 模块：问法去重
# 对知识块的问法进行规范化和去重，避免重复录入相似问题
# 支持批量去重和与已有知识库的对比
# 核心职责：确保知识库问法的唯一性，降低维护成本

import re

# 规范化正则：去除空白字符、标点符号、下划线
_STRIP_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_question(q: str) -> str:
    """
    规范化问法

    参数:
        q: 原始问法

    返回:
        规范化后的字符串（去除空白和标点、转小写）

    规范化逻辑:
        1. 去除首尾空白
        2. 转小写
        3. 去除所有空白字符、标点符号、下划线

    设计说明:
        "退货怎么办？" 和 "退货怎么办" 规范化后相同
        用于判断问法是否重复，而非作为存储格式
    """
    return _STRIP_RE.sub("", q.strip().lower())


def dedupe(items: list, existing_questions: list[str]) -> tuple[list, list]:
    """
    批量去重：内部去重 + 与已有知识库对比

    参数:
        items: 待去重的问法列表（每项有question属性）
        existing_questions: 已有知识库中的问法列表

    返回:
        (kept, discarded) 元组
        - kept: 保留的问法列表
        - discarded: 丢弃的问法列表

    去重规则:
        1. 规范化后为空的问法丢弃
        2. 已在知识库中的问法丢弃
        3. 批次内重复的问法，只保留第一次出现

    设计说明:
        先加载existing_questions到seen集合
        遍历items时检查并更新seen集合
        确保批次内的去重和跨批次的去重都准确
    """
    seen = {normalize_question(q) for q in existing_questions}
    kept, discarded = [], []
    for item in items:
        key = normalize_question(item.question)
        if not key or key in seen:
            discarded.append(item)
        else:
            seen.add(key)
            kept.append(item)
    return kept, discarded
