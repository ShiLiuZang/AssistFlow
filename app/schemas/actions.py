from typing import Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    model_validator,
)


class ResumeTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: int
    user_id: str
    confirmed: StrictBool
    tool_call_id: str | None = None


class SelectOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: int = Field(gt=0)
    user_id: str = Field(min_length=1)
    kind: Literal["select_order"] = "select_order"
    request_id: str = Field(min_length=1)
    order_id: str | None = Field(default=None, min_length=1)
    cancelled: StrictBool = False

    @model_validator(mode="after")
    def validate_choice(self):
        if self.cancelled:
            if self.order_id is not None:
                raise ValueError("取消不能同时选择订单")
        elif self.order_id is None:
            raise ValueError("请选择订单或明确取消")

        return self
