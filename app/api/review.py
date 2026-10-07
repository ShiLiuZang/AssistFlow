# 模块：审核队列API
# 提供低置信度问题的人工审核接口
# 支持查看待审队列、处理建议、通过/驳回、发布到知识库
# 核心职责：闭环飞轮流程，将人工审核的优质QA对补充回知识库

from app.core.auth import require_admin

from fastapi import Depends, APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.config import settings
from app.core.flywheel import process_pending
from app.core.trusted_sources import validate_review_source
from app.db import review_repo
from app.kb.review_publish import publish_review


router = APIRouter(dependencies=[Depends(require_admin)], prefix="/api/review", tags=["review"])

# 审核状态标签映射
LABELS = {
    "pending": "待审",
    "publishing": "发布中",
    "approved": "通过",
    "rejected": "驳回",
}
STATUS_BY_LABEL = {label: status for status, label in LABELS.items()}


class ApproveRequest(BaseModel):
    """审核通过请求体"""
    approved_answer: str = Field(min_length=1, max_length=4000)
    source_ref: str = Field(min_length=1, max_length=255)


def _display(item: dict) -> dict:
    """
    转换审核项为前端展示格式

    参数:
        item: 数据库查询的原始行字典

    返回:
        包含前端友好字段名的字典

    字段映射:
        question → normalized_question（规范化后的问题）
        suggestion → ai_suggested_answer（AI建议的答案）
        status → review_status（中文状态标签）
    """
    return {
        **item,
        "normalized_question": item["question"],
        "ai_suggested_answer": item["suggestion"],
        "review_status": LABELS[item["status"]],
    }


@router.get("/queue")
async def queue(
    status: str = "",
) -> dict:
    """
    查询审核队列

    参数:
        status: 审核状态过滤（可选），支持：待审/发布中/通过/驳回

    返回:
        包含审核项列表的字典

    设计说明:
        status为空时返回所有状态的审核项
        前端用此接口渲染待审队列和历史记录
    """
    if status and status not in STATUS_BY_LABEL:
        raise HTTPException(status_code=400, detail="审核状态无效")
    rows = await review_repo.list_review_queue(STATUS_BY_LABEL.get(status))
    return {"items": [_display(row) for row in rows]}


@router.post("/process")
async def process(
    limit: int = Query(default=20, ge=1, le=20),
) -> dict:
    """
    处理待审问题（生成AI建议答案）

    参数:
        limit: 批量处理的最大数量

    返回:
        包含处理结果统计的字典

    处理流程:
        1. 从低置信度问题池取待处理问题
        2. 检索知识库寻找相关内容
        3. 调用LLM生成建议答案
        4. 写入review_queue表，状态为pending

    设计说明:
        这是飞轮流程的第一步
        生成的建议答案需要人工审核后才能入库
    """
    return await process_pending(batch_size=limit)


@router.get("/{review_id}")
async def detail(
    review_id: int,
) -> dict:
    """
    获取审核项详情

    参数:
        review_id: 审核项ID

    返回:
        包含问题、建议答案、状态等完整信息的字典

    异常:
        404: 审核项不存在
    """
    row = await review_repo.get_review_detail(review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="审核项不存在")
    return _display(row)


@router.post("/{review_id}/reject")
async def reject(
    review_id: int,
) -> dict:
    """
    驳回审核项

    参数:
        review_id: 审核项ID

    返回:
        更新后的审核项字典

    处理逻辑:
        更新状态为rejected，记录审核人
        驳回的审核项不会入库，但保留记录用于分析

    异常:
        404: 审核项不存在
        409: 审核项状态冲突（已处理过）
    """
    try:
        reviewer = settings.review_admin_name.strip() or "local-reviewer"
        return _display(await review_repo.reject_review(review_id, reviewer))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{review_id}/approve")
async def approve(
    review_id: int,
    request: ApproveRequest,
    response: Response,
) -> dict:
    """
    通过审核项并发布到知识库

    参数:
        review_id: 审核项ID
        request: 包含审核后答案和可信材料引用的请求体
        response: 响应对象，用于设置状态码

    返回:
        更新后的审核项字典

    处理流程:
        1. 验证审核项存在
        2. 验证可信材料来源（确保答案有据可查）
        3. 更新审核项状态为approved，记录审核人、答案、材料引用
        4. 发布到知识库（写knowledge_chunks并向量化）

    容错设计:
        发布失败时返回202状态码，审核记录已保存
        前端可稍后重试发布，不需要重新审核

    异常:
        404: 审核项不存在
        409: 审核项状态冲突（已处理过）
        422: 可信材料验证失败
        503: 可信材料读取失败
    """
    answer = request.approved_answer.strip()
    source_ref = request.source_ref.strip()
    row = await review_repo.get_review_detail(review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="审核项不存在")

    # 验证可信材料：确保答案有据可查
    try:
        source_digest = validate_review_source(row["question"], answer, source_ref)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="可信材料读取失败") from exc

    # 保存审核结果
    try:
        reviewer = settings.review_admin_name.strip() or "local-reviewer"
        frozen = await review_repo.approve_review(
            review_id, reviewer, answer, source_ref, source_digest,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # 发布到知识库
    try:
        return _display(await publish_review(review_id))
    except Exception:
        # 发布失败但审核记录已保存，返回202让前端稍后重试
        response.status_code = 202
        current = await review_repo.get_review_detail(review_id)
        return _display(current or frozen)


@router.post("/{review_id}/publish")
async def retry_publish(
    review_id: int,
    response: Response,
) -> dict:
    """
    重试发布审核项到知识库

    参数:
        review_id: 审核项ID
        response: 响应对象，用于设置状态码

    返回:
        更新后的审核项字典

    使用场景:
        审核通过后发布失败（如向量化服务不可用）
        修复服务后手工重试发布

    容错设计:
        发布失败时返回202状态码
        前端可继续展示当前状态，稍后再试

    异常:
        404: 审核项不存在
        409: 审核项状态不允许发布（未审核或已驳回）
    """
    try:
        return _display(await publish_review(review_id))
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        # 发布失败，返回202和当前状态
        response.status_code = 202
        current = await review_repo.get_review_detail(review_id)
        if current is None:
            raise HTTPException(status_code=404, detail="审核项不存在")
        return _display(current)
