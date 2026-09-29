"""审核队列 API。"""

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.config import settings
from app.core.flywheel import process_pending
from app.core.trusted_sources import validate_review_source
from app.db import repository
from app.kb.review_publish import publish_review


router = APIRouter(prefix="/api/review", tags=["review"])
LABELS = {
    "pending": "待审",
    "publishing": "发布中",
    "approved": "通过",
    "rejected": "驳回",
}
STATUS_BY_LABEL = {label: status for status, label in LABELS.items()}


class ApproveRequest(BaseModel):
    approved_answer: str = Field(min_length=1, max_length=4000)
    source_ref: str = Field(min_length=1, max_length=255)


def _display(item: dict) -> dict:
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
    if status and status not in STATUS_BY_LABEL:
        raise HTTPException(status_code=400, detail="审核状态无效")
    rows = await repository.list_review_queue(STATUS_BY_LABEL.get(status))
    return {"items": [_display(row) for row in rows]}


@router.post("/process")
async def process(
    limit: int = Query(default=20, ge=1, le=20),
) -> dict:
    return await process_pending(batch_size=limit)


@router.get("/{review_id}")
async def detail(
    review_id: int,
) -> dict:
    row = await repository.get_review_detail(review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="审核项不存在")
    return _display(row)


@router.post("/{review_id}/reject")
async def reject(
    review_id: int,
) -> dict:
    try:
        reviewer = settings.review_admin_name.strip() or "local-reviewer"
        return _display(await repository.reject_review(review_id, reviewer))
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
    answer = request.approved_answer.strip()
    source_ref = request.source_ref.strip()
    row = await repository.get_review_detail(review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="审核项不存在")
    try:
        source_digest = validate_review_source(row["question"], answer, source_ref)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="可信材料读取失败") from exc
    try:
        reviewer = settings.review_admin_name.strip() or "local-reviewer"
        frozen = await repository.approve_review(
            review_id, reviewer, answer, source_ref, source_digest,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        return _display(await publish_review(review_id))
    except Exception:
        response.status_code = 202
        current = await repository.get_review_detail(review_id)
        return _display(current or frozen)


@router.post("/{review_id}/publish")
async def retry_publish(
    review_id: int,
    response: Response,
) -> dict:
    try:
        return _display(await publish_review(review_id))
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        response.status_code = 202
        current = await repository.get_review_detail(review_id)
        if current is None:
            raise HTTPException(status_code=404, detail="审核项不存在")
        return _display(current)
