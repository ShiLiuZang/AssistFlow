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

DEMO_TRACKING_NUMBERS = {
    "ORD-1001": "SF-DEMO-1001",
    "ORD-1002": "SF-DEMO-1002",
}


def get_order(order_id: str) -> dict[str, str] | None:
    """根据订单号查询演示订单，不存在时返回 None。"""
    order = DEMO_ORDERS.get(order_id)

    if order is None:
        return None

    return order.copy()


def get_user_order(order_id: str, user_id: str) -> dict[str, str] | None:
    """仅返回属于指定演示用户的订单副本。"""
    order = get_order(order_id)

    if order is None or order["user_id"] != user_id:
        return None

    return order


def get_user_tracking_no(order_id: str, user_id: str) -> str | None:
    """仅为指定用户自己的订单返回合成物流号。"""
    order = get_user_order(order_id, user_id)

    if order is None:
        return None

    return DEMO_TRACKING_NUMBERS.get(order["order_id"])


def list_user_orders(user_id: str) -> list[dict[str, str]]:
    return [
        order.copy()
        for order in DEMO_ORDERS.values()
        if order["user_id"] == user_id
    ]
