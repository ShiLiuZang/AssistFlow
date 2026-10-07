"""
测试工单确认请求的Schema验证
覆盖布尔决策的严格类型检查和工具调用ID必填约束
"""
import pytest
from pydantic import ValidationError

from app.schemas.actions import ResumeTicketRequest


def make_request(**overrides):
    """构造测试请求"""
    values = {
        "conversation_id": 1,
        "user_id": "u1",
        "confirmed": True,
        "tool_call_id": "call-1",
    }
    values.update(overrides)
    return ResumeTicketRequest(**values)


@pytest.mark.parametrize("confirmed", [True, False])
def test_resume_ticket_accepts_boolean_decisions(confirmed):
    """测试工单确认：接受True/False布尔值"""
    request = make_request(confirmed=confirmed, tool_call_id="call-1")

    assert request.confirmed is confirmed
    assert request.tool_call_id == "call-1"


@pytest.mark.parametrize("confirmed", ["true", "false", 1, 0, None])
def test_resume_ticket_rejects_coerced_decisions(confirmed):
    """测试类型验证：拒绝字符串、数字和空值的类型转换"""
    with pytest.raises(ValidationError):
        make_request(confirmed=confirmed)


def test_resume_ticket_rejects_client_tool_result():
    """测试字段保护：客户端不能直接提供tool_result"""
    with pytest.raises(ValidationError):
        make_request(tool_result={"confirmed": True, "ticket_no": "T1"})


def test_resume_ticket_rejects_missing_call_id():
    """测试必填约束：缺失tool_call_id时校验失败"""
    with pytest.raises(ValidationError) as error:
        ResumeTicketRequest(conversation_id=1, user_id="u1", confirmed=True)

    assert error.value.errors()[0]["loc"] == ("tool_call_id",)
    assert error.value.errors()[0]["type"] == "missing"
