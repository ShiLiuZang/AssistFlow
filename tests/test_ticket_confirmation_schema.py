"""
测试工单确认请求的Schema验证
覆盖布尔决策的严格类型检查和遗留兼容性
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


def test_resume_ticket_call_id_remains_optional_for_legacy_lookup():
    """测试遗留兼容：tool_call_id保持可选以支持旧版查找"""
    request = make_request()

    assert request.tool_call_id is None
