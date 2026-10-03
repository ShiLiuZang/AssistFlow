"""问题主题归类：待归类问题、归类结果写入与分布统计"""

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Message, LowConfidenceQuestion, Review, TopicClassification


def _pool_text_stmt():
    """
    构建问题池文本查询语句

    返回:
        SQLAlchemy查询语句

    设计说明:
        标准化问法对应Review.question
        关联LowConfidenceQuestion和Review表
        返回question_id, 原始问题, 标准化问题
    """
    return (
        select(LowConfidenceQuestion.id, LowConfidenceQuestion.question, Review.question)
        .outerjoin(Review, LowConfidenceQuestion.review_id == Review.id)
        .order_by(LowConfidenceQuestion.id)
    )


async def list_pool_texts() -> list[dict]:
    """
    列出问题池的所有文本

    返回:
        问题文本列表，包含question_id和text

    设计说明:
        用于主题分类和文本分析
        优先使用标准化问题（normalized），不存在时使用原始问题（raw）
    """
    async with SessionLocal() as session:
        rows = (await session.execute(_pool_text_stmt())).all()
    return [{"question_id": qid, "text": normalized or raw}
            for qid, raw, normalized in rows]


async def list_history_user_texts() -> list[dict]:
    """
    只读历史用户提问；供问题池尚为空时构建有来源标记的语料

    返回:
        用户消息列表，包含message_id, text, asked_at

    设计说明:
        用于冷启动场景，从历史对话构建训练语料
        过滤空消息和纯空白消息
    """
    statement = (
        select(Message.id, Message.content, Message.created_at)
        .where(Message.role == "user", Message.content.is_not(None))
        .order_by(Message.id)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    return [{"message_id": message_id, "text": content.strip(),
             "asked_at": created_at.isoformat(timespec="seconds") if created_at else None}
            for message_id, content, created_at in rows if content and content.strip()]


async def list_unclassified_questions(limit: int = 500) -> list[dict]:
    """
    只把已归并、尚未归类的问题送入旁路分类器

    参数:
        limit: 返回数量上限

    返回:
        未分类问题列表，包含question_id, text

    异常:
        ValueError: limit非正数

    设计说明:
        只处理已关联review_id的问题（已归并）
        排除已有分类结果的问题
        用于主题分类的增量处理
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    statement = (
        _pool_text_stmt()
        .outerjoin(TopicClassification,
                   TopicClassification.question_id == LowConfidenceQuestion.id)
        .where(TopicClassification.id.is_(None))
        .where(LowConfidenceQuestion.review_id.is_not(None))
        .limit(limit)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    return [{"question_id": qid, "text": normalized or raw}
            for qid, raw, normalized in rows]


async def insert_topic_classifications(rows: list[dict], topic_names: tuple[str, ...]) -> int:
    """
    批量插入主题分类结果

    参数:
        rows: 分类结果列表，每项包含question_id和labels
        topic_names: 合法类目（app.core.taxonomy.TOPIC_NAMES）

    返回:
        插入的记录数

    异常:
        ValueError: question_id重复或labels无效

    设计说明:
        - 验证question_id唯一性
        - 验证labels格式：非空列表、元素为有效topic、无重复
    """
    if len({row["question_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate question id in classifier batch")
    for row in rows:
        labels = row["labels"]
        if not isinstance(labels, list) or not labels or any(
            not isinstance(label, str) or label not in topic_names for label in labels
        ) or len(set(labels)) != len(labels):
            raise ValueError("invalid classifier labels")
    async with SessionLocal() as session:
        session.add_all([
            TopicClassification(question_id=row["question_id"], labels=row["labels"])
            for row in rows
        ])
        await session.commit()
    return len(rows)


async def topic_distribution(topic_names: tuple[str, ...], samples_per_class: int = 3) -> dict:
    """
    获取17类主题分布统计

    参数:
        topic_names: 类目（app.core.taxonomy.TOPIC_NAMES），按此顺序输出
        samples_per_class: 每类返回的样例数

    返回:
        分布统计字典，包含总数、最新分类时间、各类别计数和样例

    设计说明:
        直接读取本项目归类结果
        多标签问题在每个类别中都计数
        优先使用标准化问题文本
    """
    statement = (
        select(TopicClassification.labels, LowConfidenceQuestion.question,
               Review.question, TopicClassification.classified_at)
        .join(LowConfidenceQuestion,
              TopicClassification.question_id == LowConfidenceQuestion.id)
        .outerjoin(Review, LowConfidenceQuestion.review_id == Review.id)
        .order_by(TopicClassification.question_id)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    counts = {name: 0 for name in topic_names}
    samples: dict[str, list[str]] = {name: [] for name in topic_names}
    latest = None
    for labels, raw, normalized, stamp in rows:
        value = normalized or raw
        latest = stamp if latest is None or stamp > latest else latest
        for label in labels or []:
            if label in counts:
                counts[label] += 1
                if len(samples[label]) < samples_per_class and value not in samples[label]:
                    samples[label].append(value)
    return {
        "total": len(rows),
        "latest": latest.isoformat() if latest else None,
        "classes": [{"label": name, "count": counts[name], "samples": samples[name]}
                    for name in topic_names],
    }


async def topic_questions(label: str, page: int = 1, size: int = 20) -> dict:
    """
    按类目分页查询问题

    参数:
        label: 主题标签
        page: 页码（从1开始）
        size: 每页大小

    返回:
        分页结果字典，包含items, page, size, total, pages

    设计说明:
        多标签问题在每个命中类目中都可见
        返回问题详情包括分类信息、来源、归并状态等
    """
    statement = (
        select(TopicClassification.question_id, TopicClassification.labels,
               TopicClassification.classified_at, LowConfidenceQuestion.question,
               LowConfidenceQuestion.source, LowConfidenceQuestion.created_at,
               Review.question, Review.occurrence_count, Review.status)
        .join(LowConfidenceQuestion,
              TopicClassification.question_id == LowConfidenceQuestion.id)
        .outerjoin(Review, LowConfidenceQuestion.review_id == Review.id)
        .order_by(TopicClassification.question_id.desc())
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()
    hits = [row for row in rows if label in (row[1] or [])]
    pages = max(1, -(-len(hits) // size))
    page = min(page, pages)
    labels = {"pending": "待审", "publishing": "发布中",
              "approved": "通过", "rejected": "驳回"}
    items = [
        {"question_id": qid, "labels": classified,
         "text": normalized or raw, "raw_question": raw,
         "normalized": normalized is not None,
         "source": source, "occurrence_count": occurrence_count,
         "review_status": labels.get(review_status),
         "asked_at": asked.isoformat() if asked else None,
         "classified_at": stamp.isoformat() if stamp else None}
        for qid, classified, stamp, raw, source, asked, normalized,
            occurrence_count, review_status in hits[(page - 1) * size: page * size]
    ]
    return {"label": label, "total": len(hits), "page": page,
            "size": size, "pages": pages, "items": items}
