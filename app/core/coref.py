# 模块：指代消解
# 处理用户问题中的指代词（如"那个订单"、"刚才那个"），将其还原为实体
# 从当前问题和历史消息中提取订单号等实体，结合选中订单消解指代
# 核心职责：让模型理解上下文，避免"那个订单"引发的歧义

import re
from dataclasses import dataclass

# 实体模式：匹配订单号（ORD-数字；拼多多订单号为 6 位日期-一串数字）和商品型号（MH-字母数字）
ENTITY = re.compile(
    r"(?<![A-Z0-9-])(?:ORD-\d+|\d{6}-\d{10,20}|MH-[A-Z0-9]+)(?![A-Z0-9-])",
    re.I,
)

# 指代词模式：识别各种指代表达
REFERENCE = re.compile(
    r"刚才那个订单|那个订单|这个订单|那一单|这单|刚才那个|那个|这个|它"
)

def entities(text):
    """
    提取文本中的实体（订单号、商品型号）

    参数:
        text: 待提取的文本

    返回:
        实体列表，去重并保持顺序，统一转为大写

    匹配规则:
        ORD-数字：订单号
        6 位数字-一串数字：拼多多订单号
        MH-字母数字：商品型号
        前后不能紧邻字母数字或连字符，确保完整匹配
    """
    return list(
        dict.fromkeys(
            match.upper()
            for match in ENTITY.findall(text)
        )
    )

@dataclass(frozen=True)
class Resolution:
    """指代消解结果"""
    original: str  # 原始问题
    resolved: str  # 消解后的问题
    needs_clarification: bool = False  # 是否需要用户澄清

def resolve(query, history, selected_order=None):
    """
    消解问题中的指代词

    参数:
        query: 当前问题
        history: 历史消息列表（每条消息有type和content属性）
        selected_order: 用户选中的订单号（可选）

    返回:
        Resolution对象，包含原始问题、消解后问题、是否需要澄清

    消解逻辑:
        1. 检查问题中是否有指代词，无则直接返回
        2. 提取当前问题中的实体
        3. 如果当前问题无实体，从历史消息中提取
        4. 候选实体 = 当前实体 or (历史实体 + 选中订单)
        5. 候选唯一时替换指代词，否则标记需要澄清

    设计说明:
        优先使用当前问题的实体（用户可能换了话题）
        历史实体按时间顺序，最近的优先
        多个候选或无候选时都需要用户澄清，避免误解
    """
    # 无指代词直接返回
    if not REFERENCE.search(query):
        return Resolution(query, query)

    current = entities(query)

    # 从历史消息中提取实体（只看用户消息）
    historical = [
        entity
        for message in history
        if message.type == "human"
        for entity in entities(str(message.content))
    ]

    # 构建候选列表：优先当前问题的实体，否则历史+选中订单
    candidates = current or list(
        dict.fromkeys(
            historical
            + ([selected_order] if selected_order else [])
        )
    )

    # 候选不唯一时需要澄清
    if len(candidates) != 1:
        return Resolution(query, query, True)

    # 替换所有指代词为唯一候选实体
    rewritten = REFERENCE.sub(
        lambda _: candidates[0],
        query,
    )
    return Resolution(query, rewritten)