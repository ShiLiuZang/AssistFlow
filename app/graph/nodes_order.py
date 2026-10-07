"""指代消解、订单获取和订单结果节点。"""

from langgraph.types import interrupt

from app.core.coref import entities, resolve
from app.graph.state import ConversationState


def make_order_nodes(services, update) -> dict:
    """创建订单处理节点，共享状态更新函数。"""
    async def resolve_reference(state: ConversationState):
        messages = state.get("messages", [])
        covered_count = state.get("covered_count", 0)
        if not 0 <= covered_count <= len(messages):
            raise ValueError("摘要覆盖条数超出图消息范围")

        result = resolve(
            state["query"],
            messages[covered_count:],
            state.get("last_order_id") or state.get("selected_order"),
        )
        return update(
            state,
            "resolve_reference",
            query=result.original,
            resolved_query=result.resolved,
            needs_clarification=result.needs_clarification,
        )


    async def fetch_order(state: ConversationState):
        ids = [
            value
            for value in entities(state.get("resolved_query", state["query"]))
            if value.startswith("ORD-")
        ]

        if len(ids) > 1:
            return update(
                state,
                "fetch_order",
                order=None,
                route="clarify",
            )

        if ids:
            selected = ids[0]
        else:
            orders = await services.list_orders(state["user_id"])

            if not orders:
                return update(
                    state,
                    "fetch_order",
                    order=None,
                    route="no_orders",
                )

            choice = interrupt({
                "kind": "select_order",
                "request_id": state["request_id"],
                "orders": [
                    {
                        "order_id": item["order_id"],
                        "product_name": item["product_name"],
                    }
                    for item in orders
                ],
            })

            if choice.get("cancelled") is True:
                return update(
                    state,
                    "fetch_order",
                    order=None,
                    route="cancelled",
                )

            selected = choice.get("order_id")

            if selected not in {item["order_id"] for item in orders}:
                return update(
                    state,
                    "fetch_order",
                    order=None,
                    route="not_owned",
                )

        order = await services.get_order(selected)

        if (
            not order
            or order.get("user_id") != state["user_id"]
            or order.get("order_id") != selected
        ):
            return update(
                state,
                "fetch_order",
                order=None,
                route="not_owned",
            )

        return update(
            state,
            "fetch_order",
            order=dict(order),
            last_order_id=selected,
            route="policy",
        )


    async def clarify_reference(state: ConversationState):
        return update(
            state,
            "clarify_reference",
            answer="请说明你指的是哪个订单或商品。",
            citations=[],
        )


    async def order_result(state: ConversationState):
        answers = {
            "clarify": "请一次只提供一个订单号。",
            "no_orders": "没有查到你当前可选择的订单。",
            "cancelled": "已取消选择订单，本次没有继续处理。",
            "not_owned": "没有找到属于你的这笔订单，请核对订单号。",
        }

        answer = answers.get(
            state.get("route"),
            "暂时无法确认订单，请稍后重试。",
        )

        return update(
            state,
            "order_result",
            answer=answer,
            citations=[],
        )


    return {
        "resolve_reference": resolve_reference,
        "fetch_order": fetch_order,
        "clarify_reference": clarify_reference,
        "order_result": order_result,
    }
