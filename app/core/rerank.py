"""调用重排模型，对召回候选进行第二次相关性排序。"""
import math
import re
import asyncio

import httpx
from app.config import settings
from app.kb import documents


def map_result(
    hits:list[dict],
    result:list[dict],
    top_k:int,
)->list[dict]:
    """将重排结果映射回原候选，保留原始召回分。"""
    if top_k < 1:
        raise ValueError("top_k 必须为正数")
    expected_cout=min(top_k,len(hits))
    if len(result) != expected_cout:
        raise ValueError("重排结果数量不匹配")
    seen=set()
    mapped=[]
    for item in result:
        index = item["index"]
        score=float(item["relevance_score"])
        if type(index)!=int:
            raise ValueError("重排索引必须为整数")
        if not 0<=index<len(hits):
            raise ValueError("重排索引越界")

        if index in seen:
            raise ValueError("重排索引重复")

        if not math.isfinite(score):
            raise ValueError("重排分数不是有限数值")
        seen.add(index)
        mapped.append({
            **hits[index],
            "rerank_score": score,
        })
    return sorted(mapped,key=lambda x:x["rerank_score"],reverse=True)[:top_k]

def rerank_url() -> str:
    """根据配置生成重排接口地址。"""
    base = settings.rerank_base_url.rstrip("/")

    if not re.search(r"/v\d+$", base):
        base += "/v1"

    style = settings.rerank_api_style.strip().lower()

    if style not in {
        "auto",
        "singular",
        "qwen",
        "qwen3",
        "dashscope",
    }:
        raise ValueError("不支持的 RERANK_API_STYLE")

    plural = style in {"qwen", "qwen3", "dashscope"}

    if style == "auto":
        plural = "/compatible-api/" in base

    suffix = "/reranks" if plural else "/rerank"
    return base + suffix

async def post_with_retry(
    url:str,
    payload:dict,
)->dict:
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(3):
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.rerank_api_key}",
                    },
                )
                response.raise_for_status()
                return response.json()
            except (
                    httpx.TransportError,
                    httpx.HTTPStatusError,
                ) as exc:
                if isinstance(exc, httpx.TransportError):
                    transient = True
                else:
                    status = exc.response.status_code
                    transient = status == 429 or status >= 500

                if not transient or attempt == 2:
                    raise

                await asyncio.sleep(0.5 * 2 ** attempt)

async def rerank_hits(
    query: str,
    hits: list[dict],
    top_k: int,
) -> list[dict]:
    """调用重排服务，并返回映射后的知识候选。"""
    if top_k < 1:
        raise ValueError("top_k 必须为正数")

    if not hits:
        return []

    if not settings.rerank_api_key:
        raise ValueError("请先配置 RERANK_API_KEY")
    documents=[
        f"{hit['question']}\n{hit['answer']}"
        for hit in hits
    ]
    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": documents,
        "top_n": min(top_k, len(hits)),
    }
    response = await post_with_retry(
        rerank_url(),
        payload,
    )
    return map_result(
        hits,
        response["results"],
        top_k,
    )