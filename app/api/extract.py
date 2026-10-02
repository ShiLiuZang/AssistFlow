"""
结构化信息提取API路由模块

本模块提供从非结构化文本中提取结构化售后信息的接口。
核心功能：使用LLM的函数调用能力，将自然语言描述转换为带类型校验的Pydantic模型。
在系统中充当数据标准化的工具，供工单创建流程使用。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_chat_model
from app.core.prompts import EXTRACT_SYSTEM_PROMPT
from app.schemas.extract import AfterSalesTicket, ExtractRequest
from app.core.auth import current_staff
from app.core.ratelimit import limit_staff_model


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["extract"], dependencies=[Depends(current_staff)])


@router.post("/extract", response_model=AfterSalesTicket, dependencies=[Depends(limit_staff_model)])
async def extract(request: ExtractRequest) -> AfterSalesTicket:
    """
    从售后描述中提取结构化字段

    参数:
        request: ExtractRequest对象，包含待提取的文本

    返回:
        AfterSalesTicket对象，包含工单类型、描述等字段

    核心逻辑：
    1. 获取聊天模型
    2. 绑定结构化输出（使用function_calling方法）
    3. 构造系统提示词和用户消息
    4. 调用模型提取信息
    5. 返回经过Pydantic校验的结果

    边界情况：
    - 模型调用失败时返回502错误

    注意：
    该接口只提取候选信息，不创建工单
    提取结果需要进一步确认后才能创建工单
    """
    # 获取聊天模型
    model = get_chat_model()

    # 绑定结构化输出，使用function_calling方法
    extractor = model.with_structured_output(
        AfterSalesTicket,
        method="function_calling",
    )

    # 构造消息列表
    messages = [
        SystemMessage(content=EXTRACT_SYSTEM_PROMPT),
        HumanMessage(content=request.text),
    ]

    try:
        # 调用模型提取信息
        return await extractor.ainvoke(messages)
    except Exception as exc:
        logger.exception("结构化售后信息提取失败")

        raise HTTPException(
            status_code=502,
            detail="模型服务暂时不可用，请稍后重试",
        ) from exc
