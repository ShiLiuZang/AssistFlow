# 模块：工单工具
# 提供创建工单的LangChain工具，用于转人工场景
# 生成待确认的工单内容，不直接写入数据库
# 核心职责：封装工单创建逻辑，供LangGraph图节点调用

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
    """
    生成待确认的工单内容，不直接写入数据库

    参数:
        ticket_type: 工单类型（如退款、换货、投诉）
        description: 问题描述

    返回:
        包含工单信息和确认标记的字典

    返回字段:
        - requires_confirmation: True（标记需要用户确认）
        - ticket_type: 工单类型
        - description: 问题描述

    设计说明:
        模型调用此工具后返回requires_confirmation=True
        图节点拦截此标记，触发用户确认流程
        用户确认后才真正写入工单系统
        避免模型误判导致创建无效工单
    """
    return {
        "requires_confirmation": True,
        "ticket_type": ticket_type,
        "description": description,
    }
