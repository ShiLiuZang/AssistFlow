"""知识块存储、向量化状态和库存查询。"""

from sqlalchemy import func, select
from app.db import database
from app.db.models import (
    KnowledgeChunk,
)


async def insert_knowledge_chunk(
    category: str,
    questions: str,
    answer: str,
    section_path: str | None = None,
    content_type: str | None = None,
    is_key_clause: int = 0,
) -> int:
    """
    插入知识块到数据库

    参数:
        category: 知识分类
        questions: 问题文本（换行分隔多个问题）
        answer: 答案文本
        section_path: 章节路径（可选）
        content_type: 内容类型（可选）
        is_key_clause: 是否关键条款（0或1）

    返回:
        知识块ID

    设计说明:
        初始状态为pending，等待向量化流程处理
    """
    async with database.SessionLocal() as session:
        chunk = KnowledgeChunk(
            category=category,
            questions=questions,
            answer=answer,
            section_path=section_path,
            content_type=content_type,
            is_key_clause=is_key_clause,
        )
        session.add(chunk)
        await session.commit()
        await session.refresh(chunk)
        return chunk.id


async def list_pending_chunks() -> list[KnowledgeChunk]:
    """
    列出所有待向量化的知识块

    返回:
        待处理的知识块列表，按ID升序

    设计说明:
        向量化任务调度器的数据源
    """
    async with database.SessionLocal() as session:
        statement = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.vectorize_status == "pending")
            .order_by(KnowledgeChunk.id)
        )
        result = await session.scalars(statement)
        return list(result)


async def mark_chunk_vectorized(chunk_id: int, vector_id: str) -> None:
    """
    标记知识块已完成向量化

    参数:
        chunk_id: 知识块ID
        vector_id: 向量数据库中的ID

    设计说明:
        原子更新状态和向量ID，确保不会重复向量化
    """
    async with database.SessionLocal() as session:
        chunk = await session.get(KnowledgeChunk, chunk_id)
        if chunk is None:
            return
        chunk.vector_id = vector_id
        chunk.vectorize_status = "done"
        await session.commit()


async def set_chunk_neighbors(
    chunk_id: int,
    prev_id: int | None,
    next_id: int | None,
) -> None:
    """
    设置知识块的前后邻居关系

    参数:
        chunk_id: 当前知识块ID
        prev_id: 前一个知识块ID
        next_id: 后一个知识块ID

    设计说明:
        用于维护文档内知识块的顺序关系
        支持上下文连贯性检索
    """
    async with database.SessionLocal() as session:
        chunk = await session.get(KnowledgeChunk, chunk_id)
        if chunk is None:
            return
        chunk.prev_chunk_id = prev_id
        chunk.next_chunk_id = next_id
        await session.commit()


async def count_chunks_by_content_types(content_types: set[str]) -> int:
    """
    统计指定内容类型的知识块总数

    参数:
        content_types: 内容类型集合

    返回:
        匹配的知识块数量
    """
    async with database.SessionLocal() as session:
        statement = select(KnowledgeChunk).where(
            KnowledgeChunk.content_type.in_(content_types)
        )
        result = await session.scalars(statement)
        return len(list(result))


async def ensure_knowledge_chunks(chunks: list) -> list[int]:
    """
    单进程建库：复用完全相同的原文，补齐缺块和邻接关系

    参数:
        chunks: 知识块列表

    返回:
        知识块ID列表

    设计说明:
        - 一份材料在一个事务中完成
        - 旧版逐条提交留下的部分数据也能复用
        - 这是固定材料的重跑入口，不负责删除或替换已修改的旧版材料
        - 通过五元组（category, questions, answer, section_path, content_type）去重
        - 自动维护prev/next链接关系
    """
    async with database.SessionLocal() as session:
        rows = []
        used = set()
        for chunk in chunks:
            statement = select(KnowledgeChunk).where(
                KnowledgeChunk.category == chunk.category,
                KnowledgeChunk.questions == chunk.questions,
                KnowledgeChunk.answer == chunk.answer,
                KnowledgeChunk.section_path == chunk.section_path,
                KnowledgeChunk.content_type == chunk.content_type,
            ).order_by(KnowledgeChunk.id)
            matches = list(await session.scalars(statement))
            row = next((item for item in matches if item.id not in used), None)
            if row is None:
                row = KnowledgeChunk(
                    category=chunk.category, questions=chunk.questions,
                    answer=chunk.answer, section_path=chunk.section_path,
                    content_type=chunk.content_type, is_key_clause=chunk.is_key_clause,
                )
                session.add(row)
                await session.flush()
            used.add(row.id)
            rows.append(row)
        for index, row in enumerate(rows):
            row.prev_chunk_id = rows[index - 1].id if index else None
            row.next_chunk_id = rows[index + 1].id if index + 1 < len(rows) else None
        await session.commit()
        return [row.id for row in rows]


async def knowledge_stats() -> dict:
    """
    获取知识库统计信息

    返回:
        统计数据字典，包含总数、状态分布、类型分布、关键条款数

    设计说明:
        用于知识库管理面板的概览视图
    """
    async with database.SessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(KnowledgeChunk))
        by_status = dict((await session.execute(
            select(KnowledgeChunk.vectorize_status, func.count())
            .group_by(KnowledgeChunk.vectorize_status)
        )).all())
        by_type = dict((await session.execute(
            select(KnowledgeChunk.content_type, func.count())
            .group_by(KnowledgeChunk.content_type)
        )).all())
        key_clause = await session.scalar(
            select(func.count()).select_from(KnowledgeChunk)
            .where(KnowledgeChunk.is_key_clause == 1)
        )
    return {
        "total": int(total or 0),
        "pending": int(by_status.get("pending", 0)),
        "done": int(by_status.get("done", 0)),
        "by_content_type": {(key or "未标注"): int(value)
                            for key, value in by_type.items()},
        "key_clause": int(key_clause or 0),
    }


async def list_recent_chunks(limit: int = 20) -> list[KnowledgeChunk]:
    """
    列出最近的知识块

    参数:
        limit: 返回数量上限

    返回:
        知识块列表，按ID降序

    设计说明:
        用于知识库管理的最近更新视图
    """
    async with database.SessionLocal() as session:
        rows = await session.scalars(
            select(KnowledgeChunk).order_by(KnowledgeChunk.id.desc()).limit(limit)
        )
        return list(rows)


async def list_chunk_pairs() -> list[tuple[str, str]]:
    """
    列出所有知识块的问答对

    返回:
        (questions, answer)元组列表

    设计说明:
        去重键包含问题和答案
        用于去重检查和数据导出
    """
    async with database.SessionLocal() as session:
        rows = await session.execute(
            select(KnowledgeChunk.questions, KnowledgeChunk.answer)
        )
        return [(question, answer) for question, answer in rows.all()]
