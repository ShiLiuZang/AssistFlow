from langgraph.graph import END, START, StateGraph

from .nodes import make_nodes
from .routing import confidence_gate, route_by_intent, should_continue
from .state import ConversationState


def build_graph(services, checkpointer=None):
    graph = StateGraph(ConversationState)

    for name, node in make_nodes(services).items():
        graph.add_node(name, node)

    graph.add_edge(START, "resolve_reference")
    graph.add_edge("resolve_reference", "classify")
    graph.add_conditional_edges(
        "classify",
        route_by_intent,
        {
            "knowledge": "retrieve",
            "business": "agent",
            "refund": "fetch_order",
            "complaint": "complaint",
            "chat": "chat",
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
        lambda state: "policy" if state.get("route") == "policy" else "finish",
        {"policy": "policy", "finish": "finish"},
    )
    graph.add_edge("policy", "answer")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "finish": "finish",
        },
    )
    graph.add_edge("tools", "agent")
    for node in ["answer", "fallback", "complaint", "chat"]:
        graph.add_edge(node, "finish")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
