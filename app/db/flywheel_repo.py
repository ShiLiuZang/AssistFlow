"""数据飞轮：回答快照、低置信度问题池、用户反馈、问题合并"""

import json

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.db.models import Turn, LowConfidenceQuestion, Review


async def save_turn(
        owner: str,
        conversation: str,
        message_id: str,
        turn_id: str,
        question: str,
        snapshot: list | None,
) -> None:
    """
    保存回答快照。快照不可变，重复调用必须完全相同

    参数:
        owner: 用户ID
        conversation: 会话ID（字符串形式）
        message_id: 消息ID（assistant回答的稳定标识）
        turn_id: 轮次ID
        question: 原始问题
        snapshot: 检索快照列表，None表示快照丢失，[]表示检索零命中

    设计说明:
        - 快照不可变：相同message_id的重复保存必须数据完全一致
        - 用于低置信度问题的回溯分析
        - 记录检索结果以便后续改进
    """
    snapshot_json = json.dumps(snapshot, ensure_ascii=False) if snapshot is not None else None

    async with SessionLocal() as session:

        statement = select(Turn).where(
            Turn.owner == owner,
            Turn.conversation == conversation,
            Turn.message_id == message_id,
        )
        existing = await session.scalar(statement)

        if existing is not None:

            if (existing.turn_id != turn_id or
                    existing.question != question or
                    existing.snapshot != snapshot_json):
                raise ValueError("immutable turn snapshot conflict")
            return


        turn = Turn(
            owner=owner,
            conversation=conversation,
            message_id=message_id,
            turn_id=turn_id,
            question=question,
            snapshot=snapshot_json,
        )
        session.add(turn)
        await session.commit()


async def capture_low_confidence(
        owner: str,
        conversation: str,
        message_id: str,
        source: str,
        reason: str | None = None,
) -> int:
    """
    将回答落入问题池。必须先调用save_turn保存快照

    参数:
        owner: 用户ID
        conversation: 会话ID
        message_id: 消息ID
        source: 来源（retrieval_low_conf/self_check/user_feedback）
        reason: 原因描述

    返回:
        问题池记录ID

    异常:
        ValueError: source不合法
        PermissionError: 找不到对应的快照（可能是越权访问）

    设计说明:
        - 必须先调用save_turn保存快照
        - 幂等性：相同owner+conversation+message_id+source的重复调用返回首次创建的ID
        - 用于收集需要改进的问题
    """
    valid_sources = {"retrieval_low_conf", "self_check", "user_feedback"}
    if source not in valid_sources:
        raise ValueError(f"invalid source: {source}")

    async with SessionLocal() as session:

        statement = select(Turn).where(
            Turn.owner == owner,
            Turn.conversation == conversation,
            Turn.message_id == message_id,
        )
        turn = await session.scalar(statement)

        if turn is None:
            raise PermissionError("answer not found for this owner/conversation")


        pool_record = LowConfidenceQuestion(
            owner=owner,
            conversation=conversation,
            message_id=message_id,
            question=turn.question,
            snapshot=turn.snapshot,
            source=source,
            reason=reason,
        )

        session.add(pool_record)

        try:
            await session.commit()
            await session.refresh(pool_record)
            return pool_record.id
        except IntegrityError:

            await session.rollback()
            statement = select(LowConfidenceQuestion).where(
                LowConfidenceQuestion.owner == owner,
                LowConfidenceQuestion.conversation == conversation,
                LowConfidenceQuestion.message_id == message_id,
                LowConfidenceQuestion.source == source,
            )
            existing = await session.scalar(statement)
            return existing.id


async def submit_feedback(
        owner: str,
        conversation: str,
        message_id: str,
        rating: str,
) -> int | None:
    """
    提交用户反馈。只有down会落池，up不处理

    参数:
        owner: 用户ID
        conversation: 会话ID
        message_id: 消息ID
        rating: 评分（up/down）

    返回:
        问题池记录ID，如果是up则返回None

    异常:
        ValueError: rating不合法
        PermissionError: 找不到对应的快照（可能是越权访问）

    设计说明:
        - up反馈不做处理，仅记录验证权限
        - down反馈自动调用capture_low_confidence落入问题池
    """
    if rating not in {"up", "down"}:
        raise ValueError(f"invalid rating: {rating}")

    if rating == "up":
        async with SessionLocal() as session:
            turn = await session.scalar(select(Turn).where(
                Turn.owner == owner,
                Turn.conversation == conversation,
                Turn.message_id == message_id,
            ))
            if turn is None:
                raise PermissionError("answer not found for this owner/conversation")
        return None


    return await capture_low_confidence(
        owner=owner,
        conversation=conversation,
        message_id=message_id,
        source="user_feedback",
        reason="user_reports_unresolved",
    )


async def list_unmatched_questions(limit: int = 100) -> list[dict]:
    """
    查询未匹配的问题池记录

    参数:
        limit: 返回数量上限

    返回:
        未匹配的问题列表，每项包含id, question, snapshot等字段

    设计说明:
        用于问题池处理流程，筛选尚未关联到审核项的问题
    """
    async with SessionLocal() as session:
        statement = select(LowConfidenceQuestion).where(
            LowConfidenceQuestion.review_id.is_(None)
        ).order_by(LowConfidenceQuestion.id).limit(limit)

        rows = await session.scalars(statement)

        return [
            {
                "id": row.id,
                "owner": row.owner,
                "conversation": row.conversation,
                "message_id": row.message_id,
                "question": row.question,
                "snapshot": row.snapshot,
                "source": row.source,
                "reason": row.reason,
            }
            for row in rows
        ]


async def flywheel_stats() -> dict:
    """只读全量计数，区分尚未采集和已经采集但尚未归并。"""
    async with SessionLocal() as session:
        pool = await session.scalar(select(func.count()).select_from(LowConfidenceQuestion))
        unmatched = await session.scalar(select(func.count()).select_from(LowConfidenceQuestion).where(
            LowConfidenceQuestion.review_id.is_(None)))
        turns = await session.scalar(select(func.count()).select_from(Turn))
        reviews = dict((await session.execute(select(Review.status, func.count()).group_by(Review.status))).all())
    return {"saved_turns": int(turns or 0), "pool_total": int(pool or 0),
            "unmerged": int(unmatched or 0), "reviews": reviews}


async def list_review_candidates(limit: int = 101) -> list[dict]:
    """
    查询所有待审核项作为匹配候选

    参数:
        limit: 返回数量上限

    返回:
        候选列表，每项包含id, question, status

    设计说明:
        用于问题归并时提供匹配目标
        按ID降序返回最新的审核项
    """
    async with SessionLocal() as session:
        statement = select(Review).order_by(Review.id.desc()).limit(limit)
        rows = await session.scalars(statement)

        return [
            {
                "id": row.id,
                "question": row.question,
                "status": row.status,
            }
            for row in rows
        ]


async def merge_question(
    pool_id: int,
    question: str,
    suggestion: str,
    matched_id: int | None,
    offered_ids: set[int],
) -> tuple[int, str]:
    """
    原子归并：创建/加频次 + 回填游标

    参数:
        pool_id: 问题池记录ID
        question: 标准化后的问题
        suggestion: 建议回答
        matched_id: 匹配到的review_id，None表示新建
        offered_ids: 候选集合，防止幻觉ID

    返回:
        (review_id, action)
        action: "created" | "merged" | "already"

    异常:
        ValueError: 参数验证失败、幻觉ID、匹配消失等

    设计说明:
        - 事务保证：review创建/更新与问题池回填同时成功或失败
        - 幂等性：已归并的问题重复调用返回"already"
        - 防护：matched_id必须在offered_ids中，防止模型幻觉ID
        - 频次累加：相同问题归并到同一review时增加occurrences
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty string")

    if not isinstance(suggestion, str):
        raise ValueError("suggestion must be string")


    if matched_id is not None and (
        type(matched_id) is not int or matched_id not in offered_ids
    ):
        raise ValueError("hallucinated match")

    async with SessionLocal() as session:
        async with session.begin():

            statement = (
                select(LowConfidenceQuestion)
                .where(LowConfidenceQuestion.id == pool_id)
                .with_for_update()
            )
            pool_row = await session.scalar(statement)
            if pool_row is None:
                raise ValueError("missing pool row")

            if pool_row.review_id is not None:
                return pool_row.review_id, "already"


            if matched_id is None:

                review = Review(
                    question=question,
                    suggestion=suggestion,
                    occurrence_count=1,
                    status="pending",
                )
                session.add(review)
                await session.flush()
                review_id = review.id
                action = "created"
            else:

                statement = (
                    select(Review)
                    .where(Review.id == matched_id)
                    .with_for_update()
                )
                review = await session.scalar(statement)
                if review is None:
                    raise ValueError("match disappeared")

                review.occurrence_count += 1
                review_id = matched_id
                action = "merged"


            pool_row.review_id = review_id

        return review_id, action
