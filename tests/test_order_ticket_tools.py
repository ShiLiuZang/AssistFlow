"""
测试工具函数的基本功能
覆盖订单查询、工单创建、权限隔离和Schema定义
"""
from app.tools.orders import get_order
from app.tools.order_tools import query_order
from app.tools.ticket_tools import create_ticket


def test_get_existing_order():
    """测试查询存在的订单"""
    order = get_order("ORD-1001")

    assert order == {
        "order_id": "ORD-1001",
        "user_id": "u1",
        "product_name": "保温杯",
        "status": "已发货",
    }


def test_get_missing_order():
    """测试查询不存在的订单"""
    assert get_order("ORD-9999") is None


def test_query_result_cannot_change_demo_order():
    """测试演示数据不可变性：返回的订单字典修改不影响原数据"""
    order = get_order("ORD-1001")
    assert order is not None

    order["status"] = "已签收"

    queried_again = get_order("ORD-1001")
    assert queried_again is not None
    assert queried_again["status"] == "已发货"


def test_query_order_only_returns_owned_order():
    """测试订单查询权限：只能查询属于自己的订单"""
    own = query_order.invoke({"order_id": "ORD-1001", "user_id": "u1"})
    other = query_order.invoke({"order_id": "ORD-1002", "user_id": "u1"})
    missing = query_order.invoke({"order_id": "ORD-9999", "user_id": "u1"})

    assert own["found"] is True
    assert own["product_name"] == "保温杯"
    assert other == missing
    assert "product_name" not in other


def test_query_order_schema_hides_server_identity():
    """测试工具Schema：user_id不暴露给大模型"""
    assert "order_id" in query_order.args
    assert "user_id" not in query_order.args


def test_create_ticket_tool_only_builds_preview():
    """测试工单创建工具：仅生成预览，不实际创建"""
    preview = create_ticket.invoke(
        {"ticket_type": "投诉", "description": "商品包装破损"}
    )

    assert preview == {
        "requires_confirmation": True,
        "ticket_type": "投诉",
        "description": "商品包装破损",
    }
