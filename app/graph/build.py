from langgraph.graph import END, START, StateGraph

from .nodes import make_nodes
from .routing import confidence_gate, route_by_intent, should_continue
from .state import ConversationState


def build_graph(services, checkpointer=None):
    graph = StateGraph(ConversationState)

    for name, node in make_nodes(services).items():
        graph.add_node(name, node)

    graph.add_edge(START, "resolve_reference")
    graph.add_conditional_edges(
        "resolve_reference",
        lambda state: (
            "clarify"
            if state.get("needs_clarification")
            else "classify"
        ),
        {
            "clarify": "clarify_reference",
            "classify": "classify",
        },
    )
    graph.add_conditional_edges(
        "classify",
        route_by_intent,
        {
            "knowledge": "retrieve",
            "business": "agent",
            "refund": "fetch_order",
            "complaint": "complaint",
            "human": "human",
            "chat": "chat",
            "clarify": "clarify_intent",
        }
    )
    graph.add_conditional_edges(
        "retrieve",
        confidence_gate,
        {
            "answer": "answer",
            "fallback": "fallback",
        }
    )
    graph.add_conditional_edges(
        "fetch_order",
        lambda state: (
            "policy"
            if state.get("route") == "policy"
            else "reply"
        ),
        {
            "policy": "policy",
            "reply": "order_result",
        },
    )
    graph.add_conditional_edges(
        "policy",
        confidence_gate,
        {
            "answer": "answer",
            "fallback": "fallback",
        },
    )
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "finish": "finish",
        },
    )
    graph.add_edge("tools", "agent")
    for node in [
        "answer",
        "fallback",
        "complaint",
        "chat",
        "clarify_reference",
        "order_result",
        "human",
        "clarify_intent",
    ]:
        graph.add_edge(node, "finish")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
