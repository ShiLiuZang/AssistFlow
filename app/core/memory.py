# 模块：对话记忆管理
# 管理多轮对话的消息窗口，支持按token预算截取最近轮次
# 校验消息合法性（角色、顺序、工具调用完整性）
# 核心职责：确保输入模型的对话历史格式正确且在预算内

import json
from dataclasses import dataclass

@dataclass(frozen=True)
class Message:
    """对话消息"""
    id: int  # 消息ID，必须递增
    role: str  # 角色：human/ai/tool
    content: str  # 消息内容
    calls: tuple[str, ...] = ()  # AI消息发起的工具调用ID列表
    call_id: str | None = None  # tool消息对应的调用ID

def group_turns(messages):
    """
    按对话轮次分组

    参数:
        messages: 消息列表

    返回:
        轮次列表，每轮以human消息开头

    设计说明:
        简单按human消息切分，不校验合法性
        用于非严格场景（如估算、展示）
    """
    groups = []
    current = []
    for message in messages:
        role = message.role
        if role == "human" and current:
            groups.append(current)
            current = []
        current.append(message)
    if current:
        groups.append(current)
    return groups

def estimate(messages):
    """
    估算消息列表的token数

    参数:
        messages: 消息列表

    返回:
        估算的字符数（粗略等价于token数）

    估算方法:
        JSON序列化长度 + 每条消息8字符开销

    设计说明:
        快速估算，不调用tokenizer
        用于窗口截取时的预算控制
    """
    return sum(
        len(json.dumps(message.__dict__, ensure_ascii=False)) + 8
        for message in messages
    )
def turns(messages):
    """
    严格校验对话轮次并分组

    参数:
        messages: 消息列表

    返回:
        轮次列表，每轮以human消息开头

    校验规则:
        1. 消息ID必须严格递增
        2. 对话必须以human消息开头
        3. human消息之间不能有未完成的工具调用
        4. tool消息必须有对应的调用ID
        5. AI消息的calls不能有重复
        6. 角色只能是human/ai/tool

    异常:
        ValueError: 违反任一校验规则

    设计说明:
        严格校验确保消息序列合法，避免模型输入格式错误
        工具调用完整性检查防止遗漏tool消息
    """
    groups = []
    pending = set()  # 待返回的工具调用ID
    previous = 0
    for message in messages:
        if message.id <= previous:
            raise ValueError("message IDs must increase")
        previous = message.id
        if message.role == "human":
            if pending:
                raise ValueError("unfinished tool calls")
            groups.append([])
        elif message.role == "tool":
            if message.call_id not in pending:
                raise ValueError("orphan or duplicate tool result")
            pending.remove(message.call_id)
        elif message.role == "ai":
            if pending:
                raise ValueError("tool results missing")
            if len(set(message.calls)) != len(message.calls):
                raise ValueError("duplicate call IDs")
            pending.update(message.calls)
        else:
            raise ValueError("history only accepts human/ai/tool")

        if not groups:
            raise ValueError("history must begin with human")
        groups[-1].append(message)
    if pending:
        raise ValueError("finish tool execution before model input")

    return groups

def build_window(messages, budget, reserve=0, keep=3, count=estimate):
    """
    构建对话窗口：在预算内保留最近若干轮

    参数:
        messages: 消息列表
        budget: 总预算（字符数或token数）
        reserve: 保留空间（留给系统提示词等）
        keep: 至少保留的轮次数
        count: 计数函数（默认estimate）

    返回:
        截取后的消息列表

    截取策略:
        1. 校验并分组为轮次
        2. 从最近keep轮开始，逐轮向前扩展
        3. 每次扩展检查是否超预算（含保留空间）
        4. 超预算时停止扩展，返回已收集的消息

    异常:
        ValueError: 预算/保留空间非法，或当前轮超预算

    设计说明:
        keep确保至少保留当前轮和最近几轮，避免丢失关键上下文
        reserve预留空间给系统提示词、摘要等固定开销
        从后向前扩展确保最近的对话优先保留
    """
    if budget <= reserve or reserve < 0 or keep < 1:
        raise ValueError("invalid budget or window")

    groups = turns(messages)
    result = []
    for group in reversed(groups[-keep:]):
        candidate = group + result
        if count(candidate) + reserve > budget:
            if not result:
                raise ValueError("current turn exceeds budget")
            break
        result = candidate
    return result
