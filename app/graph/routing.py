"""
LangGraph 路由决策模块

本模块提供 LangGraph 条件边的路由函数，根据状态动态决定下一个节点。
主要路由函数：
1. route_by_intent: 根据意图路由到不同处理分支
2. confidence_gate: 根据检索置信度决定是否直接回答
3. should_continue: 判断 Agent 是否需要继续调用工具

路由函数是 LangGraph 条件边的核心，它们读取状态并返回下一个节点名称。
"""

from typing import Literal

from .state import ConversationState


def route_by_intent(
    state: ConversationState,
) -> Literal[
    "knowledge",
    "business",
    "refund",
    "complaint",
    "human",
    "chat",
    "clarify",
]:
    """
    根据意图路由到不同处理分支

    读取状态中的 route 字段（由 classify 节点设置），决定下一步处理流程。

    Args:
        state: 对话状态

    Returns:
        下一个节点名称：
        - knowledge: 知识查询（需要检索知识库）
        - business: 业务操作（需要调用工具，如订单查询、物流追踪）
        - refund: 退款申请（需要订单处理和政策检索）
        - complaint: 投诉处理
        - human: 转人工客服
        - chat: 闲聊
        - clarify: 意图不明确，需要澄清

    如果 route 不在预定义集合中，默认返回 "clarify"（保守策略）。
    """
    route = state.get("route")

    # 校验 route 是否为有效值
    if route in {
        "knowledge",
        "business",
        "refund",
        "complaint",
        "human",
        "chat",
        "clarify",
    }:
        return route

    # 默认返回 clarify（意图不明确）
    return "clarify"


def confidence_gate(
    state: ConversationState,
) -> Literal["answer", "fallback"]:
    """
    置信度门控函数

    根据检索结果的置信度决定是否直接生成答案。
    如果置信度足够高，进入 answer 节点生成答案；
    否则进入 fallback 节点进行降级处理（记录低置信度问题）。

    Args:
        state: 对话状态

    Returns:
        下一个节点名称：
        - answer: 置信度高，直接生成答案
        - fallback: 置信度低，降级处理（记录到低置信度问题池）

    判断逻辑：
    1. evidence_allowed 必须为 True（某些意图不需要检索）
    2. evidence 列表非空（至少有检索结果）

    注：置信度评估在 retrieve 或 policy 节点中完成，这里只检查结果。
    """
    if (
        state.get("evidence_allowed") is True
        and state.get("evidence")
    ):
        return "answer"

    return "fallback"


def should_continue(state: ConversationState) -> Literal["tools", "finish"]:
    """
    判断 Agent 是否需要继续调用工具

    Agent 节点生成 assistant 消息后，检查是否包含 tool_calls。
    如果有工具调用请求，路由到 tools 节点执行工具；
    否则认为 Agent 已完成任务，路由到 finish 节点。

    Args:
        state: 对话状态

    Returns:
        下一个节点名称：
        - tools: 需要调用工具
        - finish: 任务已完成，不需要工具

    这是 Agent 模式的核心循环：agent → tools → agent → ... → finish
    """
    messages = state.get("messages")
    if not messages:
        return "finish"

    # 获取最后一条消息（应该是 assistant 消息）
    last_message = messages[-1]

    # 检查是否有工具调用（tool_calls 属性）
    tool_call = getattr(last_message, "tool_calls", [])
    if tool_call:
        return "tools"

    return "finish"
