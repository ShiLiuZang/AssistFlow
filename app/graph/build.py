"""
LangGraph 对话图构建模块

本模块负责构建智能客服系统的对话流程图（StateGraph）。
对话图定义了用户请求的处理流程，包括：
1. 意图识别和路由
2. 知识库检索
3. 订单处理
4. 工具调用（Agent 模式）
5. 答案生成

图结构：
- 节点（Node）：处理逻辑单元（如意图分类、检索、答案生成）
- 边（Edge）：节点间的转换关系
- 条件边（Conditional Edge）：根据状态动态选择下一个节点

参考 git commit 9faaac0 (接入多轮订单选择与退款政策子流程)
参考 git commit 6721ca3 (统一服务端工具身份上下文)
"""

from langgraph.graph import END, START, StateGraph

from .nodes import make_nodes
from .routing import confidence_gate, route_by_intent, should_continue
from .state import ConversationState


def build_graph(services, checkpointer=None):
    """
    构建对话流程图

    Args:
        services: 服务容器，包含 LLM、工具注册表、审计回调等
        checkpointer: 检查点持久化器，用于保存和恢复会话状态（支持断点续传）

    Returns:
        编译后的 StateGraph 对象，可直接调用处理请求

    图流程说明：
    1. START → resolve_reference: 指代消解（将"它"、"那个订单"替换为具体实体）
    2. resolve_reference → classify/clarify_reference: 如果查询模糊则澄清，否则分类意图
    3. classify → 根据意图路由到不同分支：
       - knowledge: 知识库查询 → retrieve → answer/fallback
       - refund: 退款流程 → fetch_order → policy/order_result
       - business: Agent 模式 → 调用工具 → finish
       - complaint/human/chat: 直接回复 → finish
    4. 所有分支最终汇聚到 finish → END
    """
    # 创建状态图（基于 ConversationState）
    graph = StateGraph(ConversationState)

    # 添加所有节点（从 make_nodes 获取节点字典）
    for name, node in make_nodes(services).items():
        graph.add_node(name, node)

    # ==================== 指代消解入口 ====================
    # START 直接进入 resolve_reference 节点
    # 参考 git commit b406062 (增加保守指代消解并保留用户原话)
    graph.add_edge(START, "resolve_reference")

    # resolve_reference 根据是否需要澄清来路由
    graph.add_conditional_edges(
        "resolve_reference",
        lambda state: (
            "clarify"
            if state.get("needs_clarification")  # 查询模糊，需要澄清
            else "classify"  # 查询明确，进入意图分类
        ),
        {
            "clarify": "clarify_reference",  # 澄清节点（询问用户具体指什么）
            "classify": "classify",  # 意图分类节点
        },
    )

    # ==================== 意图分类和路由 ====================
    # 根据识别的意图路由到不同处理分支
    # 参考 git commit 4d1384a (记录意图与选单接入审查)
    graph.add_conditional_edges(
        "classify",
        route_by_intent,  # 路由函数，根据 intent 字段决定下一个节点
        {
            "knowledge": "retrieve",  # 知识查询 → 检索节点
            "business": "agent",  # 业务操作（需要工具调用）→ Agent 节点
            "refund": "fetch_order",  # 退款申请 → 订单获取节点
            "complaint": "complaint",  # 投诉 → 投诉处理节点
            "human": "human",  # 转人工 → 人工客服节点
            "chat": "chat",  # 闲聊 → 闲聊节点
            "clarify": "clarify_intent",  # 意图不明确 → 意图澄清节点
        }
    )

    # ==================== 知识检索分支 ====================
    # 检索后根据置信度决定是否直接回答
    graph.add_conditional_edges(
        "retrieve",
        confidence_gate,  # 置信度门控函数
        {
            "answer": "answer",  # 置信度高 → 直接生成答案
            "fallback": "fallback",  # 置信度低 → 降级处理（记录低置信度问题）
        }
    )

    # ==================== 订单处理分支 ====================
    # 参考 git commit 9faaac0 (接入多轮订单选择与退款政策子流程)
    graph.add_conditional_edges(
        "fetch_order",
        lambda state: (
            "policy"  # 如果需要查询退款政策
            if state.get("route") == "policy"
            else "reply"  # 否则直接返回订单结果
        ),
        {
            "policy": "policy",  # 政策检索节点（查询退款规则）
            "reply": "order_result",  # 订单结果节点（返回订单详情）
        },
    )

    # 政策检索后也需要置信度门控
    graph.add_conditional_edges(
        "policy",
        confidence_gate,
        {
            "answer": "answer",
            "fallback": "fallback",
        },
    )

    # ==================== Agent 工具调用分支 ====================
    # Agent 节点调用工具后可能需要继续调用（多轮工具调用）
    graph.add_conditional_edges(
        "agent",
        should_continue,  # 判断是否需要继续调用工具
        {
            "tools": "tools",  # 需要调用工具 → 工具执行节点
            "finish": "finish",  # 不需要工具或已完成 → 结束节点
        },
    )

    # 工具执行完毕后返回 agent 节点（继续决策）
    graph.add_edge("tools", "agent")

    # ==================== 所有分支汇聚到 finish ====================
    # 以下节点完成后直接进入 finish 节点
    for node in [
        "answer",  # 答案生成节点
        "fallback",  # 降级处理节点
        "complaint",  # 投诉处理节点
        "chat",  # 闲聊节点
        "clarify_reference",  # 指代澄清节点
        "order_result",  # 订单结果节点
        "human",  # 人工客服节点
        "clarify_intent",  # 意图澄清节点
    ]:
        graph.add_edge(node, "finish")

    # finish 节点完成后结束图
    graph.add_edge("finish", END)

    # 编译图并返回（如果提供了 checkpointer，则启用状态持久化）
    return graph.compile(checkpointer=checkpointer)
