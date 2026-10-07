"""
测试意图分类的核心逻辑
覆盖低置信度处理、意图路由映射、置信度边界验证和异常回退
"""
import asyncio
import pytest

from app.core.intent import Intent, Prediction, ROUTES, classify
from pydantic import ValidationError


def test_low_confidence_keeps_prediction():
    """测试低置信度处理：保留预测但路由到澄清节点"""
    async def fake_predict(query):
        assert query == "帮我查一下订单"
        return {
            "intent": "订单",
            "confidence": 0.2,
        }

    result, route = asyncio.run(
        classify("帮我查一下订单", fake_predict)
    )

    assert result.intent == Intent.ORDER
    assert result.confidence == 0.2
    assert route == "clarify"


@pytest.mark.parametrize("label, route", [
    ("物流", "business"), ("订单", "business"),
    ("商品咨询", "knowledge"), ("退款退货", "refund"),
    ("售后", "refund"), ("投诉", "complaint"),
    ("人工", "human"), ("闲聊", "chat"), ("其他", "clarify"),
])
def test_labels_and_routes(label, route):
    """测试意图标签与路由的映射关系"""
    assert set(ROUTES) == set(Intent)
    assert len(Intent) == 9
    assert ROUTES[Intent(label)] == route


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_confidence_includes_endpoints(confidence):
    """测试置信度边界：接受0.0和1.0"""
    assert Prediction(intent="订单", confidence=confidence).confidence == confidence


@pytest.mark.parametrize("raw", [
    {"intent": "订单", "confidence": -0.1},
    {"intent": "订单", "confidence": 1.1},
    {"intent": "订单", "confidence": "0.9"},
    {"intent": "订单", "confidence": True},
    {"intent": "订单", "confidence": float("nan")},
    {"intent": "订单", "confidence": float("inf")},
    {"intent": "不存在", "confidence": 0.9},
    {"intent": "订单", "confidence": 0.9, "extra": "value"},
    {"intent": "订单"},
])
def test_invalid_prediction_falls_back(raw):
    """测试异常预测回退：非法数据触发验证错误"""
    with pytest.raises(ValidationError):
        Prediction.model_validate(raw)

    async def predict(query):
        return raw

    result, route = asyncio.run(classify("查订单", predict))
    assert result.intent == Intent.OTHER
    assert result.confidence == 0.0
    assert route == "clarify"
