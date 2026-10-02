"""
内容安全

1. 输出拦截：最终回复里出现模型无权做出的办理承诺（已退款、保证赔付等）时整条替换为安全话术。
   系统当前不能执行真实退款，提示词已经禁止这类说法，这里是确定性的最后一道防线。
2. 个人信息脱敏：手机号、邮箱、身份证、长单号、微信/QQ、收货地址、标注出来的姓名。
   挖掘语料、作业日志和应用日志共用同一套规则。
"""

import logging
import re

# ==================== 输出拦截 ====================

SAFE_REPLY = (
    "抱歉，我暂时无法直接为您办理退款或承诺赔付。"
    "您可以在订单页提交售后申请，或回复「转人工」由客服为您处理。"
)

# 只匹配“已经办成/作出承诺”的说法，不拦“退款需要 3 天到账”这类政策解释
_FORBIDDEN_CLAIMS = [
    re.compile(r"(已|已经)(为您|给您|帮您)?(成功)?(办理|完成|发起|申请)?(了)?(退款|退货退款|赔付|补偿)(成功|完成)?(了)?"),
    re.compile(r"退款(已经?|已)(成功|完成|到账|退回|原路退回)"),
    re.compile(r"(保证|承诺|一定)(会)?(给您|为您)?(全额)?(退款|赔付|赔偿|补偿)"),
    re.compile(r"(我|我们)(已|已经|马上|立即|现在就)?(为您|给您|帮您)(退款|赔付|打款|补发现金)"),
]


_NEGATION = re.compile(r"(不|无法|没有|没|未|并非|不会|不能)[^，。！？,.!?]{0,4}$")


def violates_policy(text: str) -> bool:
    """命中承诺说法且前面没有否定词（「无法保证退款」「不能为您退款」不算）。"""
    compact = re.sub(r"\s+", "", text or "")
    for pattern in _FORBIDDEN_CLAIMS:
        for match in pattern.finditer(compact):
            if not _NEGATION.search(compact[max(0, match.start() - 6):match.start()]):
                return True
    return False


def guard_reply(text: str) -> tuple[str, bool]:
    """返回 (可发出的回复, 是否被替换)。"""
    if text and violates_policy(text):
        return SAFE_REPLY, True
    return text, False


# ==================== 个人信息脱敏 ====================

_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_CN_ID = re.compile(r"(?<!\d)[1-9]\d{16}[\dXx](?!\w)")
_LONG_DIGITS = re.compile(r"\d{10,}")
_WX_QQ = re.compile(r"(微信|weixin|wx|QQ|qq)[号:: ]*[A-Za-z0-9_-]{5,}\s?")
# 收货地址：省/市/区县开头，接街道、路、号、栋、单元、室等门牌信息
_ADDRESS = re.compile(
    r"[一-龥]{2,8}(?:省|自治区|市)"
    r"[一-龥A-Za-z0-9 ]{0,30}?"
    r"(?:区|县|市|镇|乡|街道)"
    r"[一-龥A-Za-z0-9\-#（）() ]{0,40}?"
    r"(?:路|街|道|巷|弄|村|小区|大厦|花园|苑)"
    r"[一-龥A-Za-z0-9\-#（）() ]{0,20}?"
    r"(?:\s*\d+\s*(?:号|栋|幢|座|单元|室|楼|层))+"
)
# 只脱敏明确标注的姓名，不做自由文本人名识别（误伤太大）
_LABELED_NAME = re.compile(r"((?:姓名|收件人|收货人|联系人)\s*[:：]?\s*)[一-龥·]{2,5}")


def desensitize(text: str) -> str:
    """地址和标注姓名先处理，避免其中的门牌号被当成其他模式；其余顺序与原微调语料脱敏一致。"""
    text = _ADDRESS.sub("[地址]", text)
    text = _LABELED_NAME.sub(lambda m: m.group(1) + "[姓名]", text)
    text = _PHONE.sub("[手机号]", text)
    text = _EMAIL.sub("[邮箱]", text)
    text = _CN_ID.sub("[身份证号]", text)
    text = _LONG_DIGITS.sub("[单号]", text)
    text = _WX_QQ.sub(lambda m: m.group(1) + "[账号]", text)
    return text


class DesensitizeFilter(logging.Filter):
    """应用日志输出前脱敏：先把参数格式化进消息，再整体脱敏。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        cleaned = desensitize(message)
        if cleaned != message or record.args:
            record.msg, record.args = cleaned, None
        return True


_factory_installed = False


def install_log_redaction() -> None:
    """让进程内所有日志记录在创建时就脱敏（幂等）。

    用记录工厂而不是 handler 过滤器：应用日志可能经由根 logger、uvicorn 的 handler
    或 lastResort 输出，工厂能覆盖全部路径。
    """
    global _factory_installed
    if _factory_installed:
        return
    previous = logging.getLogRecordFactory()
    redact = DesensitizeFilter()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        redact.filter(record)
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True
