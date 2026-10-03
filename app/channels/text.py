"""
渠道消息文本处理

平台聊天窗口只显示纯文本：去掉 Markdown 和引用编号，按句子拆成不超过上限的几条。
网页里用按钮完成的操作（确认建单、选择订单），在渠道里改成文字提示，买家回文字。
"""

import re

_CITATION = re.compile(r"\s?\[\d+\]")
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\([^)\s]+\)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.M)
_EMPHASIS = re.compile(r"(\*\*|__|`+)")
_BLANK_LINES = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")

MAX_PARTS = 4
TRUNCATED_TAIL = "（内容较多，您可以告诉我具体想了解哪一点）"


def plain_text(text: str) -> str:
    """Markdown 转纯文本，去掉 [1] 这类引用编号。"""
    text = _CITATION.sub("", text or "")
    text = _MD_LINK.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _BULLET.sub("· ", text)
    text = _EMPHASIS.sub("", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def split_message(text: str, limit: int, max_parts: int = MAX_PARTS) -> list[str]:
    """按段落、句子拆成每条不超过 limit 字；最多 max_parts 条，超出部分截断并提示。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > limit:  # 单句超长时硬切
            pieces.append(sentence[:limit])
            sentence = sentence[limit:]
        if sentence:
            pieces.append(sentence)
    parts: list[str] = []
    current = ""
    for piece in pieces:
        if len(current) + len(piece) > limit and current.strip():
            parts.append(current.strip())
            current = ""
        current += piece
    if current.strip():
        parts.append(current.strip())
    if len(parts) > max_parts:
        last = parts[max_parts - 1]
        room = limit - len(TRUNCATED_TAIL)
        parts = parts[:max_parts - 1] + [last[:room].rstrip() + TRUNCATED_TAIL]
    return parts


# ==================== 待确认操作 ====================

_YES = re.compile(r"^(确认|确定|是的?|好的?|好滴|可以|行|同意|提交|创建|要|嗯+|对|ok|yes|y|1)[!！。.~～啊呀吧的]*$", re.I)
_NO = re.compile(r"^(取消|不用了?|不要了?|不需要|算了|否|不|no|n|0)[!！。.~～啊呀吧的]*$", re.I)


def ticket_prompt(preview: dict) -> str:
    ticket_type = str(preview.get("ticket_type") or "售后").strip()
    description = str(preview.get("description") or "").strip()
    lines = [f"将为您提交「{ticket_type}」工单："]
    if description:
        lines.append(description)
    lines.append("回复「确认」提交，回复「取消」放弃。")
    return "\n".join(lines)


def parse_confirmation(text: str) -> bool | None:
    """买家对建单提示的回复：True 确认，False 取消，None 没看懂。"""
    compact = re.sub(r"\s+", "", text or "")
    if _YES.match(compact):
        return True
    if _NO.match(compact):
        return False
    return None


def order_prompt(orders: list[dict]) -> str:
    lines = ["您想咨询哪一笔订单？回复序号即可："]
    for index, order in enumerate(orders, 1):
        name = order.get("product_name") or ""
        lines.append(f"{index}. {name} {order.get('order_id', '')}".replace("  ", " "))
    lines.append("回复「取消」不选。")
    return "\n".join(lines)


def parse_order_choice(text: str, orders: list[dict]) -> str | bool | None:
    """返回选中的订单号；买家取消返回 False；看不懂返回 None。"""
    compact = re.sub(r"\s+", "", text or "")
    if _NO.match(compact):
        return False
    for order in orders:
        if order.get("order_id") and order["order_id"] in compact:
            return order["order_id"]
    match = re.fullmatch(r"第?(\d{1,2})(个|笔|单)?", compact)
    if match and 1 <= int(match.group(1)) <= len(orders):
        return orders[int(match.group(1)) - 1]["order_id"]
    return None
