from typing import Literal
import json
from pathlib import Path
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.retrieval import search_knowledge
from app.core.evidence import answer_from_hits



router = APIRouter(tags=["knowledge"])
REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "04.json"
EVAL_LOCK = asyncio.Lock()


def load_cases():
    from scripts.eval_04 import validate_cases, ROOT
    cases = [json.loads(line) for line in
             (ROOT / "tests/data/eval_04.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    validate_cases(cases)
    return cases


@router.get("/api/knowledge/cases")
async def cases():
    return {"cases": load_cases()}


class EvaluationRequest(BaseModel):
    top_k: int = Field(default=5, ge=1, le=50)
    generate: bool = False


@router.post("/api/knowledge/evaluate")
async def run_evaluation(request: EvaluationRequest):
    from app.core.evaluation import evaluate
    if EVAL_LOCK.locked():
        raise HTTPException(409, "评测正在运行，请稍后刷新报告")
    async with EVAL_LOCK:
        dataset = load_cases()
        try:
            result = await asyncio.wait_for(
                evaluate(dataset, k=request.top_k, generate=request.generate), timeout=600)
        except TimeoutError as exc:
            raise HTTPException(504, "评测超时，请检查检索服务；本次未覆盖旧报告") from exc
        result.update(created_at=datetime.now(timezone.utc).isoformat(), dataset=dataset)
        REPORT_PATH.parent.mkdir(exist_ok=True)
        temporary = REPORT_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(REPORT_PATH)
        return result


@router.get("/rag-eval")
async def evaluation_page(request: Request):
    if "text/html" in request.headers.get("accept", ""):
        return FileResponse(Path(__file__).resolve().parents[1] / "static" / "rageval.html")
    return await report()


@router.get("/api/rag-eval/report")
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
