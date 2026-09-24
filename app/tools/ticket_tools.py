from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field


@tool
def create_ticket(
    ticket_type: Annotated[
        str,
        Field(min_length=1, description="工单类型，例如退款、换货或投诉"),
    ],
    description: Annotated[
        str,
        Field(min_length=1, description="需要客服处理的问题描述"),
    ],
) -> dict[str, object]:
    """生成待确认的工单内容，不直接写入数据库。"""
    return {
        "requires_confirmation": True,
        "ticket_type": ticket_type,
        "description": description,
    }
