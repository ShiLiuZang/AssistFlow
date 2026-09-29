"""
LangGraph 对话状态定义

本模块定义 ConversationState，它是 LangGraph 对话图的核心数据结构。
状态在节点之间传递，每个节点可以读取和更新状态字段。

状态管理特性：
1. 消息历史：使用 add_messages reducer 自动合并消息
2. 意图和路由：记录用户意图、置信度和路由决策
3. 检索上下文：存储检索证据、快照和置信度信号
4. 订单处理：支持订单选择和指代消解（参考 git commit d4386aa）
5. 对话摘要：滚动摘要文本和覆盖位置（参考 git commit c5c2aad）

参考 git commit 1c67061 (区分本轮状态与已验证订单槽位)
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ConversationState(
    TypedDict,
    total=False,  # 允许部分字段缺失（不是所有字段都必需）
):
    """
    对话状态类

    定义 LangGraph 对话图在节点间传递的所有状态字段。
    使用 TypedDict 提供类型提示，total=False 表示字段可选。
    """

    # ==================== 消息历史 ====================
    messages: Annotated[
        list[AnyMessage],
        add_messages,  # 使用 LangGraph 的 add_messages reducer，自动合并新消息
    ]  # 对话消息列表（user、assistant、tool 消息）

    # ==================== 用户查询 ====================
    query: str  # 原始用户查询

    # ==================== 会话标识 ====================
    user_id: str  # 用户 ID

    conversation_id: str  # 会话 ID

    # ==================== 意图识别 ====================
    intent: str  # 识别出的用户意图（如 "查询订单", "退款申请"）

    # ==================== 检索证据 ====================
    evidence: list[dict]  # 检索到的证据列表（知识库分块）
    evidence_confidence: float | None  # 证据置信度得分
    confidence_signals: dict | None  # 置信度信号详情（用于调试和分析）
    retrieved_snapshot: list[dict] | None  # 检索结果快照（用于记录和回放）
    evidence_allowed: bool  # 是否允许使用检索证据（某些意图不需要检索）
    fallback_source: str | None  # 降级来源（如果检索失败）
    fallback_reason: str | None  # 降级原因

    # ==================== 生成答案 ====================
    answer: str  # 生成的答案文本

    # ==================== 引用来源 ====================
    citations: list[dict]  # 答案引用的知识来源列表

    # ==================== 执行控制 ====================
    steps: int  # 已执行步骤数（用于防止无限循环）

    # ==================== 调试追踪 ====================
    trace: list[str]  # 执行轨迹（节点调用顺序）

    # ==================== 指代消解 ====================
    resolved_query: str  # 消解后的查询（替换代词为实体）
    needs_clarification: bool  # 是否需要澄清（查询模糊）

    # ==================== 订单处理 ====================
    # 参考 git commit d4386aa (增加订单选择节点与归属校验)
    selected_order: str  # 用户选择的订单 ID（通过序号或订单号）
    order: dict | None  # 当前操作的订单详情
    last_order_id: str  # 上一次提及的订单 ID（用于指代消解）

    # ==================== 查询理解 ====================
    queries: list[str]  # 子查询列表（复杂问题拆分后）

    # ==================== 请求追踪 ====================
    request_id: str  # 请求唯一 ID（用于追踪和关联）

    # ==================== 路由决策 ====================
    route: str  # 路由目标节点名称
    intent_detail: str  # 意图详情（细分类别）
    intent_confidence: float  # 意图识别置信度

    # ==================== 对话摘要 ====================
    # 参考 git commit c5c2aad (按覆盖游标更新滚动摘要)
    summary_text: str  # 滚动摘要文本
    summary_upto: int  # 摘要覆盖到的消息 ID
    covered_count: int  # 已覆盖的消息数量

    # ==================== 消息标识 ====================
    message_id: str | None  # 当前消息 ID（用于关联 Turn 快照）
