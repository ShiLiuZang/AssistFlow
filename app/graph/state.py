from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ConversationState(
    TypedDict,  # 基类：定义一个带字段类型说明的字典
    total=False,  # 类参数：所有字段都允许暂时缺省
):
    messages: Annotated[
        list[AnyMessage],  # 类型参数：消息列表，元素可以是任意 LangChain 消息
        add_messages,  # 合并规则：追加新消息，或按消息 ID 更新旧消息
    ]

    query: str
    # 当前轮用户问题

    user_id: str
    # 当前用户的演示身份
    conversation_id: str

    intent: str
    # 当前轮意图，例如 knowledge、business、chat

    evidence: list[dict]
    # 当前轮检索到的证据

    answer: str
    # 当前轮最终回答

    citations: list[dict]
    # 当前回答引用的证据来源

    steps: int
    # 当前轮工具循环执行次数

    trace: list[str]
    # 当前轮经过的节点名称
    resolved_query: str
    needs_clarification: bool
    selected_order: str
    order: dict | None
    last_order_id: str
    queries: list[str]
    request_id: str
    route: str
    intent_detail: str
    intent_confidence: float
    summary_text: str
    summary_upto: int
    covered_count: int
