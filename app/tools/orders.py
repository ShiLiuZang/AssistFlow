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


# ==================== 外部订单来源 ====================
# 外部渠道（如拼多多）的顾客查的是平台订单，不是演示数据。
# 来源按顾客 ID / 订单号认领；都不认领时回到上面的演示数据。

class OrderProvider:
    def handles_user(self, user_id: str) -> bool:
        return False

    def handles_order(self, order_id: str) -> bool:
        return False

    async def get(self, order_id: str) -> dict | None:
        """返回订单（含 user_id，节点据此做归属校验）；不存在或无权查询返回 None。"""
        return None

    async def list_for_user(self, user_id: str) -> list[dict]:
        return []


_providers: list[OrderProvider] = []


def register_provider(provider: OrderProvider) -> None:
    if provider not in _providers:
        _providers.append(provider)


def unregister_provider(provider: OrderProvider) -> None:
    if provider in _providers:
        _providers.remove(provider)


def provider_for_order(order_id: str) -> OrderProvider | None:
    return next((p for p in _providers if p.handles_order(order_id)), None)


def provider_for_user(user_id: str) -> OrderProvider | None:
    return next((p for p in _providers if p.handles_user(user_id)), None)


async def find_order(order_id: str) -> dict | None:
    provider = provider_for_order(order_id)
    return await provider.get(order_id) if provider else get_order(order_id)


async def find_user_orders(user_id: str) -> list[dict]:
    provider = provider_for_user(user_id)
    return await provider.list_for_user(user_id) if provider else list_user_orders(user_id)
