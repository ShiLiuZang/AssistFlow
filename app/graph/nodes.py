"""
LangGraph 节点实现模块

本模块实现对话图的所有节点逻辑。每个节点是一个处理单元，负责：
1. 读取状态（ConversationState）
2. 执行特定逻辑（意图识别、检索、答案生成等）
3. 更新状态并返回

主要节点：
- classify: 意图分类和路由
- resolve_reference: 指代消解（将"它"替换为具体实体）
- retrieve: 知识库检索
- answer: 答案生成
- agent: Agent 工具调用决策
- tools: 工具执行
- fetch_order: 订单获取和选择
- policy: 退款政策检索
- finish: 最终处理（记录日志、更新摘要）
"""


import json

from langchain_core.messages import AIMessage

from app.core.observability import span
from app.graph.nodes_agent import make_agent_nodes
from app.graph.nodes_order import make_order_nodes
from app.graph.nodes_rag import make_rag_nodes
from app.graph.state import ConversationState


def make_nodes(services):
    """
    创建所有节点的工厂函数

    根据服务容器（services）创建对话图的所有节点。
    服务容器包含：
    - LLM 调用服务（classify、answer 等）
    - 检索服务（retrieve_detailed、retrieve_policy_detailed）
    - 工具注册表（tool_registry）
    - 审计和追踪回调（audit_sink、trace_sink）

    Args:
        services: 服务容器对象

    Returns:
        节点字典，键为节点名称，值为节点函数

    Raises:
        ValueError: 如果 max_steps < 1
    """
    if services.max_steps < 1:
        raise ValueError("max_steps 必须为正数")

    # 获取追踪回调（用于记录执行追踪 span）
    trace_sink = getattr(services, "trace_sink", None)

    def update(state: ConversationState, name: str, **values):
        """
        更新状态的辅助函数

        在状态中追加节点名称到 trace 列表，并更新其他字段。

        Args:
            state: 当前状态
            name: 节点名称
            **values: 要更新的字段

        Returns:
            包含更新字段的字典
        """
        return {
            "trace": [*state.get("trace", []), name],  # 追加节点名称到轨迹
            **values,
        }


    async def classify(state: ConversationState):
        messages = state.get("messages", [])
        covered_count = state.get("covered_count", 0)
        uncovered = messages[covered_count:]
        recent_context = [
            {"role": message.type, "content": str(message.content)[:800]}
            for message in uncovered[:-1]
            if message.type in {"human", "ai"} and message.content
        ][-4:]
        async with span("classify", trace_sink) as record:
            prediction, route = await services.classify(
                state.get("resolved_query") or state["query"],
                summary_text=state.get("summary_text", ""),
                recent_context=recent_context,
            )
            record["intent"] = prediction.intent.value
            record["intent_confidence"] = prediction.confidence
        legacy = {
            "knowledge": "knowledge",
            "business": "business",
            "refund": "business",
            "complaint": "complaint",
            "human": "chat",
            "chat": "chat",
            "clarify": "chat",
        }

        return update(
            state,
            "classify",
            intent=legacy[route],
            intent_detail=prediction.intent.value,
            intent_confidence=prediction.confidence,
            route=route,
        )


    async def chat(state: ConversationState):
        return update(
            state,
            "chat",
            answer="你好，可以咨询商品知识、订单或售后问题。"
        )


    async def complaint(state: ConversationState):
        return update(
            state,
            "complaint",
            answer="已了解你的投诉，请通过订单售后入口联系人工客服处理。",
        )


    async def human(state: ConversationState):
        return update(
            state,
            "human",
            answer="如需人工协助，请通过订单售后入口联系人工客服。",
            citations=[],
        )


    async def clarify_intent(state: ConversationState):
        return update(
            state,
            "clarify_intent",
            answer="请补充你希望办理的事情，例如查询订单、咨询商品或申请售后。",
            citations=[],
        )


    async def finish(state: ConversationState):
        if state.get("intent") == "business":
            messages = []
            decisions = []
            for message in reversed(state.get("messages", [])):
                if message.type == "human":
                    break
                if message.type == "tool":
                    result = json.loads(message.content)
                    if isinstance(result, dict) and "confirmed" in result:
                        decisions.append(
                            f"工单已创建，工单号：{result['ticket_no']}"
                            if result["confirmed"] else "已取消，本次没有创建工单。"
                        )

            if decisions:

                answer = "\n".join(reversed(decisions))
                messages = [AIMessage(content=answer, id=state["messages"][-1].id)]
                return update(state, "finish", messages=messages, answer=answer)
            answer=state.get("answer","")
            history = state.get("messages",[])
            last_message=history[-1] if history else None
            answer_already_present=(
                getattr(last_message,"type",None)=="ai"
                and str(last_message.content)==answer
            )
            if answer and not answer_already_present:
                messages = [
                    AIMessage(
                        content=answer,
                        id=state.get("message_id"),
                    )
                ]
        else:
            messages = [
                AIMessage(
                    content=state["answer"],
                    id=state.get("message_id"),
                )
            ]

        return update(
            state,
            "finish",
            messages=messages,
        )


    nodes = {
        **make_rag_nodes(services, update, trace_sink),
        **make_agent_nodes(services, update, trace_sink),
        **make_order_nodes(services, update),
        "complaint": complaint,
        "chat": chat,
        "classify": classify,
        "finish": finish,
        "human": human,
        "clarify_intent": clarify_intent,
    }
    # 保持原有节点注册顺序。
    return {
        name: nodes[name]
        for name in (
            "retrieve",
            "answer",
            "fallback",
            "agent",
            "tools",
            "complaint",
            "chat",
            "classify",
            "finish",
            "resolve_reference",
            "fetch_order",
            "policy",
            "clarify_reference",
            "order_result",
            "human",
            "clarify_intent",
        )
    }
