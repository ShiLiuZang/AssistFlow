from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ExtractRequest(BaseModel):
    """POST /api/extract 的请求体。"""

    text: str = Field(
        min_length=1,
        description="用户的售后描述原文",
    )


class RequestType(str, Enum):
    """售后诉求允许使用的固定分类。"""

    REFUND = "退款"
    EXCHANGE = "换货"
    REPAIR = "维修"
    COMPLAINT = "投诉"
    OTHER = "其他"


class AfterSalesTicket(BaseModel):
    """从用户原文提取的候选字段，不代表已经创建真实工单。"""

    order_id: str | None = Field(
        default=None,
        description="订单号；原文没有出现时必须为 null，禁止编造",
    )
    request_type: RequestType = Field(
        description="用户的售后诉求类型",
    )
    expected_solution: str = Field(
        min_length=1,
        description="用一句话概括用户期待的处理方案",
    )

    @field_validator("order_id", mode="before")
    @classmethod
    def normalize_missing_order_id(cls, value: object) -> object:
        """把模型返回的常见缺失占位词统一转换为 None。"""
        if isinstance(value, str) and value.strip().lower() in {
            "",
            "null",
            "none",
            "n/a",
            "无",
        }:
            return None

        return value
