"""知识审核和可恢复的发布状态存储。"""

import json
from sqlalchemy import select
from datetime import datetime, timezone
from app.db import database
from app.db.models import (
    KnowledgeChunk, LowConfidenceQuestion, Review,
)


def _review_data(row: Review) -> dict:
    """
    将Review对象转换为字典

    参数:
        row: Review对象

    返回:
        审核项字典

    设计说明:
        统一的序列化方法，确保API返回格式一致
    """
    return {
        "id": row.id,
        "question": row.question,
        "suggestion": row.suggestion,
        "occurrence_count": row.occurrence_count,
        "status": row.status,
        "reviewer": row.reviewer,
        "answer": row.answer,
        "source_ref": row.source_ref,
        "source_digest": row.source_digest,
        "publish_error": row.publish_error,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def list_review_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    """
    列出审核队列

    参数:
        status: 状态过滤（pending/publishing/approved/rejected），None表示全部
        limit: 返回数量上限（1-100）

    返回:
        审核项列表，按ID降序

    异常:
        ValueError: 参数验证失败

    设计说明:
        用于审核管理面板的列表视图
    """
    if status not in {None, "pending", "publishing", "approved", "rejected"}:
        raise ValueError("invalid review status")
    if limit < 1 or limit > 100:
        raise ValueError("invalid review limit")
    async with database.SessionLocal() as session:
        statement = select(Review)
        if status is not None:
            statement = statement.where(Review.status == status)
        rows = await session.scalars(statement.order_by(Review.id.desc()).limit(limit))
        return [_review_data(row) for row in rows]


async def get_review_detail(review_id: int) -> dict | None:
    """
    获取审核项详情

    参数:
        review_id: 审核项ID

    返回:
        审核项详细信息，不存在时返回None

    设计说明:
        包含关联的问题池记录，用于审核决策
    """
    async with database.SessionLocal() as session:
        review = await session.get(Review, review_id)
        if review is None:
            return None
        statement = (
            select(LowConfidenceQuestion)
            .where(LowConfidenceQuestion.review_id == review_id)
            .order_by(LowConfidenceQuestion.id)
        )
        rows = await session.scalars(statement)
        return {
            **_review_data(review),
            "raws": [
                {
                    "id": row.id,
                    "raw_question": row.question,
                    "source": row.source,
                    "reason": row.reason,
                    "retrieved_chunks": json.loads(row.snapshot) if row.snapshot is not None else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ],
        }


async def reject_review(review_id: int, reviewer: str) -> dict:
    """
    驳回审核项

    参数:
        review_id: 审核项ID
        reviewer: 审核人

    返回:
        更新后的审核项

    异常:
        ValueError: 参数验证失败或状态不符
        LookupError: 审核项不存在

    设计说明:
        - 只能驳回pending状态的审核项
        - 已驳回的重复调用幂等返回
        - 记录审核人和审核时间
    """
    if not reviewer.strip():
        raise ValueError("审核人不能为空")
    async with database.SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            if review.status == "rejected":
                return _review_data(review)
            if review.status != "pending":
                raise ValueError("只有待审项可以驳回")
            review.status = "rejected"
            review.reviewer = reviewer
            review.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            return _review_data(review)


async def approve_review(
    review_id: int,
    reviewer: str,
    answer: str,
    source_ref: str,
    source_digest: str,
) -> dict:
    """
    核准审核项

    参数:
        review_id: 审核项ID
        reviewer: 审核人
        answer: 核准的答案
        source_ref: 来源引用
        source_digest: 材料版本SHA256

    返回:
        更新后的审核项

    异常:
        ValueError: 参数验证失败或状态不符
        LookupError: 审核项不存在

    设计说明:
        - 只能核准pending状态的审核项
        - 核准后状态变为publishing，等待发布
        - 已publishing/approved的重复调用需参数完全一致才幂等
        - 已冻结的审核项不能修改，需新建修订
        - source_digest用于版本控制，防止基于过期材料审核
    """
    if not reviewer.strip() or not answer.strip() or not source_ref.strip():
        raise ValueError("审核人、核准答案和来源不能为空")
    if len(source_digest) != 64:
        raise ValueError("材料版本无效")
    async with database.SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            if review.status in {"publishing", "approved"}:
                if (
                    review.reviewer == reviewer
                    and review.answer == answer
                    and review.source_ref == source_ref
                    and review.source_digest == source_digest
                ):
                    return _review_data(review)
                raise ValueError("审核内容已冻结，修改答案需新建修订")
            if review.status != "pending":
                raise ValueError("已驳回项不能核准")
            review.status = "publishing"
            review.reviewer = reviewer
            review.answer = answer
            review.source_ref = source_ref
            review.source_digest = source_digest
            review.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            return _review_data(review)


def _publish_chunk_data(row: KnowledgeChunk) -> dict:
    """
    将知识块对象转换为发布数据字典

    参数:
        row: KnowledgeChunk对象

    返回:
        发布数据字典

    设计说明:
        用于审核发布流程的数据传递
    """
    return {
        "id": row.id,
        "review_id": row.review_id,
        "category": row.category,
        "question": row.questions,
        "answer": row.answer,
        "section_path": row.section_path,
        "content_type": row.content_type,
        "vectorize_status": row.vectorize_status,
    }


async def prepare_review_chunk(review_id: int, content_type: str) -> dict:
    """
    SQL事务里复用或创建一个冻结审核项对应的知识块

    参数:
        review_id: 审核项ID
        content_type: 内容类型

    返回:
        知识块数据字典

    异常:
        LookupError: 审核项不存在
        ValueError: 状态不符或数据不一致

    设计说明:
        - 事务保证：审核项和知识块状态一致
        - 幂等性：已存在的知识块会被复用
        - 一致性校验：复用时验证问答内容是否与审核项一致
        - 知识块初始状态为pending，等待向量化
    """
    async with database.SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            if review.status not in {"publishing", "approved"}:
                raise ValueError("审核项尚未核准")
            if not review.answer or not review.source_ref or not review.source_digest:
                raise ValueError("审核依据不完整")
            chunk = await session.scalar(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.review_id == review_id)
                .with_for_update()
            )
            if chunk is None:
                chunk = KnowledgeChunk(
                    review_id=review_id,
                    category="审核问答",
                    questions=review.question,
                    answer=review.answer,
                    section_path=f"{review.source_ref} / 审核问答",
                    content_type=content_type,
                    vectorize_status="pending",
                )
                session.add(chunk)
                await session.flush()
            elif chunk.questions != review.question or chunk.answer != review.answer:
                raise ValueError("已冻结知识块内容与审核项不一致")
            return _publish_chunk_data(chunk)


async def finish_review_publish(review_id: int, chunk_id: int) -> dict:
    """
    只在目标向量可见后调用；审核状态和SQL向量状态一起提交

    参数:
        review_id: 审核项ID
        chunk_id: 知识块ID

    返回:
        更新后的审核项

    异常:
        LookupError: 审核项不存在
        ValueError: 状态不符或关联无效

    设计说明:
        - 事务保证：审核状态和知识块向量化状态原子更新
        - 调用时机：向量已写入Milvus且可检索后
        - 清除错误标记：发布成功后清空publish_error
    """
    async with database.SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is None:
                raise LookupError("review not found")
            chunk = await session.scalar(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.review_id == review_id)
                .with_for_update()
            )
            if chunk is None or chunk.id != chunk_id:
                raise ValueError("审核知识块关联无效")
            if review.status not in {"publishing", "approved"}:
                raise ValueError("审核项状态不允许发布")
            chunk.vector_id = str(chunk.id)
            chunk.vectorize_status = "done"
            review.status = "approved"
            review.publish_error = None
            return _review_data(review)


async def note_review_publish_error(review_id: int, code: str) -> None:
    """
    记录审核发布错误

    参数:
        review_id: 审核项ID
        code: 错误代码

    设计说明:
        - 只记录publishing状态的审核项错误
        - 错误代码截断到255字符
        - 用于故障诊断和重试逻辑
    """
    async with database.SessionLocal() as session:
        async with session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            if review is not None and review.status == "publishing":
                review.publish_error = code[:255]
