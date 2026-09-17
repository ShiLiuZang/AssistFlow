import logging

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_chat_model
from app.core.prompts import EXTRACT_SYSTEM_PROMPT
from app.schemas.extract import AfterSalesTicket, ExtractRequest


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract", response_model=AfterSalesTicket)
async def extract(request: ExtractRequest) -> AfterSalesTicket:
    """把一段售后描述提取成经过 Pydantic 校验的固定字段。

    该接口只提取候选信息，不创建工单；上游模型失败时返回 HTTP 502。
    """
    model = get_chat_model()
    # 当前供应商不支持默认 response_format，显式使用工具调用生成结构化结果。
    extractor = model.with_structured_output(
        AfterSalesTicket,
        method="function_calling",
    )

    messages = [
        SystemMessage(content=EXTRACT_SYSTEM_PROMPT),
        HumanMessage(content=request.text),
    ]

    try:
        return await extractor.ainvoke(messages)
    except Exception as exc:
        logger.exception("结构化售后信息提取失败")

        raise HTTPException(
            status_code=502,
            detail="模型服务暂时不可用，请稍后重试",
        ) from exc
