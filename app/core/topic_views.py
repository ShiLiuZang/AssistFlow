"""主题页统一读取业务归类表；未迁移时读取隔离的历史会话归类。"""

import asyncio

from sqlalchemy.exc import SQLAlchemyError

from app.core import history_topics
from app.db import topic_repo


async def distribution() -> dict:
    try:
        result = await topic_repo.topic_distribution()
        if result["total"] or not history_topics.available():
            return result
    except SQLAlchemyError:
        if not history_topics.available():
            raise
    return await asyncio.to_thread(history_topics.distribution)


async def questions(label: str, page: int = 1, size: int = 20) -> dict:
    try:
        business = await topic_repo.topic_distribution()
        if business["total"] or not history_topics.available():
            return await topic_repo.topic_questions(label, page=page, size=size)
    except SQLAlchemyError:
        if not history_topics.available():
            raise
    return await asyncio.to_thread(history_topics.questions, label, page, size)
