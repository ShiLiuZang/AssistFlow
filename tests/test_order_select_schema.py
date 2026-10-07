"""
测试订单选择的请求Schema验证
覆盖有效选择、取消操作和各种非法输入的拒绝
"""
import pytest
from pydantic import ValidationError

from app.schemas.actions import SelectOrderRequest


@pytest.mark.parametrize("choice", [{"order_id": "ORD-1001"}, {"cancelled": True}])
def test_valid_selection_or_cancellation(choice):
    """测试有效的订单选择或取消请求"""
    request = SelectOrderRequest(conversation_id=1, user_id="u1", request_id="r1", **choice)
    assert request.kind == "select_order"


@pytest.mark.parametrize("choice", [
    {}, {"order_id": ""}, {"cancelled": "true"}, {"cancelled": 1},
    {"cancelled": True, "order_id": "ORD-1001"},
    {"order_id": "ORD-1001", "confirmed": True},
    {"order_id": "ORD-1001", "kind": "confirm_ticket"},
])
def test_reject_invalid_selection(choice):
    """测试拒绝非法选择：空值、类型错误、字段冲突等"""
    with pytest.raises(ValidationError):
        SelectOrderRequest(conversation_id=1, user_id="u1", request_id="r1", **choice)
