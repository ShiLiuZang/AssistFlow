"""
知识库检索与评测API路由模块

本模块提供知识库检索、答案生成和RAG系统评测的接口。
核心功能包括：向量/BM25/混合检索、基于检索结果生成答案、运行评测集并生成报告。
在系统中充当RAG系统的测试和调试入口，供开发人员评估检索效果和答案质量。
"""

from typing import Literal
import json
from pathlib import Path
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.kb.retrieval import search_knowledge
from app.core.evidence import answer_from_hits
from app.core.auth import current_staff, require_admin
from app.core.ratelimit import limit_staff_model


router = APIRouter(tags=["knowledge"], dependencies=[Depends(current_staff)])

# 评测报告存储路径
REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "04.json"

# 评测锁，防止并发评测
EVAL_LOCK = asyncio.Lock()


def load_cases():
    """
    加载评测用例集

    返回:
        评测用例列表，每个用例包含query、expected_chunks等字段

    从data/eval/04.jsonl读取用例，调用validate_cases校验格式
    """
    from scripts.eval_04 import validate_cases, ROOT
    cases = [json.loads(line) for line in
             (ROOT / "data/eval/04.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    validate_cases(cases)
    return cases


@router.get("/api/knowledge/cases")
async def cases():
    """
    获取所有评测用例

    返回:
        包含cases字段的字典，供前端展示评测集内容
    """
    return {"cases": load_cases()}


class EvaluationRequest(BaseModel):
    """
    评测请求参数模型

    属性:
        top_k: 检索返回的文档数量，默认5
        generate: 是否生成答案（True时会调用LLM生成答案并评估）
    """
    top_k: int = Field(default=5, ge=1, le=50)
    generate: bool = False


@router.get("/api/knowledge/evaluation-state")
async def evaluation_state():
    """返回现有评测锁与报告版本，供页面核对长请求；不启动评测。"""
    return {"running": EVAL_LOCK.locked(),
            "report_mtime": REPORT_PATH.stat().st_mtime if REPORT_PATH.exists() else None}


@router.post("/api/knowledge/evaluate", dependencies=[Depends(require_admin)])
async def run_evaluation(request: EvaluationRequest):
    """
    运行知识库评测

    参数:
        request: EvaluationRequest对象

    返回:
        评测结果字典，包含recall、precision、mrr等指标

    核心逻辑：
    1. 获取评测锁，防止并发评测
    2. 加载评测用例集
    3. 调用evaluate函数执行评测（设置600秒超时）
    4. 将结果写入报告文件（使用临时文件+原子替换，防止写入失败损坏报告）
    5. 返回评测结果

    边界情况：
    - 已有评测正在运行时返回409
    - 评测超时时返回504，不覆盖旧报告

    为什么需要锁：
    评测是重量级操作，并发执行会导致资源争抢和结果混乱
    """
    from app.kb.evaluation import evaluate

    # 检查是否有评测正在运行
    if EVAL_LOCK.locked():
        raise HTTPException(409, "评测正在运行，请稍后刷新报告")

    async with EVAL_LOCK:
        dataset = load_cases()
        try:
            # 执行评测，设置600秒超时
            result = await asyncio.wait_for(
                evaluate(dataset, k=request.top_k, generate=request.generate), timeout=600)
        except TimeoutError as exc:
            raise HTTPException(504, "评测超时，请检查检索服务；本次未覆盖旧报告") from exc

        # 添加元数据
        result.update(created_at=datetime.now(timezone.utc).isoformat(), dataset=dataset)

        # 写入报告文件（使用临时文件+原子替换）
        REPORT_PATH.parent.mkdir(exist_ok=True)
        temporary = REPORT_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(REPORT_PATH)

        return result


@router.get("/rag-eval")
async def evaluation_page():
    """RAG 评测报告（兼容旧地址，等同 /api/rag-eval/report）。"""
    return await report()


@router.get("/api/rag-eval/report")
async def report():
    """
    获取最新的评测报告

    返回:
        评测报告JSON对象，包含各项指标和详细结果

    如果报告文件不存在，返回not_evaluated状态
    """
    if not REPORT_PATH.exists():
        return {"status": "not_evaluated", "message": "尚未评估"}
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


class KnowledgeRequest(BaseModel):
    """
    知识库检索请求参数模型

    属性:
        query: 查询文本
        strategy: 检索策略（vector/bm25/hybrid/hybrid_rerank）
        top_k: 返回文档数量
        category: 分类过滤（可选）
        rewrite: 是否查询重写
        split: 是否分句检索
    """
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
    """
    执行知识库检索

    参数:
        request: KnowledgeRequest对象

    返回:
        检索结果列表，每个结果包含chunk_id、text、score等字段

    直接调用search_knowledge函数，捕获异常并返回502错误
    供前端调试检索效果使用
    """
    try:
        return await search_knowledge(**request.model_dump())
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="检索调用失败，请检查服务配置",
        ) from exc


@router.post("/api/knowledge/answer", dependencies=[Depends(limit_staff_model)])
async def answer(request: KnowledgeRequest):
    """
    基于检索结果生成答案

    参数:
        request: KnowledgeRequest对象

    返回:
        答案对象，包含answer字段和引用信息

    核心逻辑：
    1. 先调用search接口获取检索结果
    2. 调用answer_from_hits基于检索结果生成答案

    供前端测试端到端的RAG流程使用
    """
    # 先执行检索
    hits = await search(request)

    try:
        # 基于检索结果生成答案
        return await answer_from_hits(request.query, hits)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="生成调用失败，请检查服务配置",
        ) from exc
