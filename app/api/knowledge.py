from typing import Literal
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.retrieval import search_knowledge
from app.core.evidence import answer_from_hits



router = APIRouter(tags=["knowledge"])
REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "04.json"


@router.get("/rag-eval")
async def report():
    """没有真实评测报告时明确返回尚未评估。"""
    if not REPORT_PATH.exists():
        return {"status": "not_evaluated", "message": "尚未评估"}
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))



class KnowledgeRequest(BaseModel):
    query: str = Field(min_length=1)
    strategy: Literal[
        "vector", "bm25", "hybrid", "hybrid_rerank"
    ] = "vector"
    top_k: int = Field(default=5, ge=1, le=50)
    category: str | None = None
    rewrite: bool = False
    split: bool = False

@router.post("/api/knowledge/search")
async def search(request: KnowledgeRequest):
    try:
        return await search_knowledge(**request.model_dump())
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="检索调用失败，请检查服务配置",
        ) from exc
@router.post("/api/knowledge/answer")
async def answer(request: KnowledgeRequest):
    hits = await search(request)

    try:
        return await answer_from_hits(request.query, hits)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="生成调用失败，请检查服务配置",
        ) from exc
