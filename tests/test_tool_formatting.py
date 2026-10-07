"""
测试物流结果的格式化和字段过滤
覆盖状态码翻译、未知状态保留、非法字段拒绝
"""
from copy import deepcopy

import pytest

from app.tools.formatting import format_logistics_result


def test_known_status_is_translated_and_extra_fields_are_removed():
    """测试已知状态翻译：转换为中文并移除额外字段"""
    data = {
        "status_code": "IN_TRANSIT",
        "status": "远端自定义文案",
        "tracking_no": "SF-DEMO-1001",
        "recipient_phone": "synthetic-phone",
        "address": "synthetic-address",
        "internal": {"notes": "private"},
    }
    original = deepcopy(data)

    result = format_logistics_result(data)

    assert result == {
        "status_code": "IN_TRANSIT",
        "status": "运输中",
        "tracking_no": "SF-DEMO-1001",
    }
    assert data == original


def test_unknown_status_is_preserved_without_guessing():
    """测试未知状态保留：不做猜测，直接使用原状态码"""
    assert format_logistics_result({"status_code": "CUSTOMS_HOLD"}) == {
        "status_code": "CUSTOMS_HOLD",
        "status": "CUSTOMS_HOLD",
    }


@pytest.mark.parametrize("data", [
    {},
    {"status_code": None},
    {"status_code": ""},
    {"status_code": "   "},
    {"status_code": 123},
    {"status_code": ["IN_TRANSIT"]},
    {"status_code": "IN_TRANSIT", "tracking_no": 123},
])
def test_invalid_logistics_fields_are_rejected(data):
    """测试非法字段拒绝：缺失、空值、类型错误"""
    with pytest.raises(ValueError):
        format_logistics_result(data)


def test_optional_null_tracking_number_is_omitted():
    """测试可选字段：tracking_no为None时省略"""
    assert format_logistics_result({
        "status_code": "IN_TRANSIT", "tracking_no": None,
    }) == {"status_code": "IN_TRANSIT", "status": "运输中"}
