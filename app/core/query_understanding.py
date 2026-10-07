"""问题改写与关键词扩展。"""

import logging
import re

from pydantic import BaseModel, Field

from app.core.llm import get_chat_model
from app.core.observability import extract_model_name, extract_token_usage, span
logger = logging.getLogger(__name__)


class Rewrite(BaseModel):
    standard:str
    expanded: list[str] = Field(default_factory=list)


def extract_models(text: str) -> set[str]:
    """提取商品型号，统一转成大写后比较。"""
    return set(
        re.findall(r"MH-[A-Z0-9]+", text.upper())
    )

async def understand(query: str)->dict:
    """生成标准问法与扩展词，失败时使用原问题。"""
    try:
        model = get_chat_model().with_structured_output(
            Rewrite,
            method="function_calling",
            include_raw=True,
        )
        messages = [
            (
                "system",
                "将用户问题改写为适合知识检索的标准问法，"
                "保持原意，保留型号、数字和否定含义。"
                "另外给出最多五个同义或近义检索词。"
                "不得回答问题，不得补充用户未提供的事实。",
            ),
            ("human", query),
        ]
        async with span("query_rewrite_model", generation=True) as record:
            response = await model.ainvoke(messages)
            raw = response["raw"]

            usage = extract_token_usage(raw)
            if usage is not None:
                record["token_usage"] = usage

            model_name = extract_model_name(raw)
            if model_name is not None:
                record["model"] = model_name

            parsing_error = response["parsing_error"]
            if parsing_error is not None:
                raise parsing_error

            result = response["parsed"]
            if result is None:
                raise ValueError("问题改写模型未返回可解析的结果")

        standard=result.standard.strip() or query
        original_models = extract_models(query)
        if extract_models(standard) != original_models:
            raise ValueError("改写改变了商品型号")
        expanded = [
            word.strip()
            for word in result.expanded
            if word.strip()
               and extract_models(word).issubset(original_models)
        ][:5]
        return {
            "standard": standard,
            "expanded": expanded,
        }
    except Exception:
        logger.warning(
            "问题改写失败，使用原问题",
            exc_info=True,
        )

        return {
            "standard": query,
            "expanded": [],
        }
