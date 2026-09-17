"""供模型使用的订单查询工具。"""

from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool
from pydantic import Field

from app.tools.orders import get_order

@tool
def query_order(
    order_id: Annotated[
        str,
        Field(description="需要查询的订单号，例如 ORD-1001"),

    ],
    user_id: Annotated[str, InjectedToolArg],
) -> dict[str, object]:
    """查询订单的商品名称和当前状态。"""
    order = get_order(order_id)
    if order is None or order["user_id"] != user_id:
        return {
            "found": False,
            "error": "没有找到您的这笔订单",
            "code": "order_not_owned",
        }

    return {
        "found": True,
        "order_id": order["order_id"],
        "product_name": order["product_name"],
        "status": order["status"],
    }