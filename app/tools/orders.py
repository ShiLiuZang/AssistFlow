"""稳定的演示订单数据和查询函数。"""

DEMO_ORDERS = {
    "ORD-1001": {
        "order_id": "ORD-1001",
        "user_id": "u1",
        "product_name": "保温杯",
        "status": "已发货",
    },
    "ORD-1002": {
        "order_id": "ORD-1002",
        "user_id": "u2",
        "product_name": "机械键盘",
        "status": "待发货",
    },
}


def get_order(order_id: str) -> dict[str, str] | None:
    """根据订单号查询演示订单，不存在时返回 None。"""
    order = DEMO_ORDERS.get(order_id)

    if order is None:
        return None

    return order.copy()