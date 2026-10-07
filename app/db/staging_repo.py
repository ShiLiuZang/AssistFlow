"""知识候选暂存区的库存和状态查询。"""

from sqlalchemy import func, select
from app.db import database
from app.db.models import (
    QaExtractionStaging,
)


STAGING_STATUSES = ("extracted", "kept", "discarded", "approved", "rejected")


async def staging_stats() -> dict:
    """
    获取QA提取暂存区统计信息

    返回:
        统计数据字典，包含各状态计数、总数、批次数、最新批次号

    设计说明:
        用于QA提取管理面板的概览视图
    """
    async with database.SessionLocal() as session:
        counts = dict((await session.execute(
            select(QaExtractionStaging.status, func.count())
            .group_by(QaExtractionStaging.status)
        )).all())
        batches = await session.scalar(
            select(func.count(func.distinct(QaExtractionStaging.batch_no)))
        )
        latest = await session.scalar(
            select(QaExtractionStaging.batch_no)
            .order_by(QaExtractionStaging.id.desc()).limit(1)
        )
    return {
        "counts": {key: int(counts.get(key, 0))
                   for key in STAGING_STATUSES},
        "total": sum(int(value) for value in counts.values()),
        "batches": int(batches or 0),
        "latest_batch": latest,
    }


async def list_staging_by_status(status: str) -> list[QaExtractionStaging]:
    """
    按状态列出暂存区记录

    参数:
        status: 状态（extracted/kept/discarded/approved/rejected）

    返回:
        暂存区记录列表，按ID升序

    设计说明:
        用于QA提取的人工审核流程
    """
    async with database.SessionLocal() as session:
        rows = await session.scalars(
            select(QaExtractionStaging)
            .where(QaExtractionStaging.status == status)
            .order_by(QaExtractionStaging.id)
        )
        return list(rows)


async def list_staging_by_ids(
    ids: list[int], status: str | None = None,
) -> list[QaExtractionStaging]:
    """
    按ID列表查询暂存区记录

    参数:
        ids: ID列表
        status: 可选状态过滤

    返回:
        暂存区记录列表，按ID升序

    设计说明:
        用于批量操作时的数据获取
    """
    if not ids:
        return []
    async with database.SessionLocal() as session:
        query = select(QaExtractionStaging).where(QaExtractionStaging.id.in_(ids))
        if status is not None:
            query = query.where(QaExtractionStaging.status == status)
        rows = await session.scalars(query.order_by(QaExtractionStaging.id))
        return list(rows)


async def set_staging_status(ids: list[int], status: str) -> None:
    """
    批量设置暂存区记录状态

    参数:
        ids: ID列表
        status: 目标状态

    设计说明:
        - 事务保证：全部更新或全部失败
        - 行级锁：防止并发冲突
        - 用于批量保留/丢弃操作
    """
    if not ids:
        return
    async with database.SessionLocal() as session:
        async with session.begin():
            rows = await session.scalars(
                select(QaExtractionStaging)
                .where(QaExtractionStaging.id.in_(ids))
                .with_for_update()
            )
            for row in rows:
                row.status = status
