# 模块：历史会话主题归类存储
# 管理历史会话的主题分类结果，使用SQLite隔离存储
# 支持批量写入、分布统计、按主题分页查询
# 核心职责：独立存储历史会话归类结果，与问题池归类分离


import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.core.taxonomy import TOPIC_NAMES


# 独立的SQLite数据库，与主MySQL库隔离
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "finetune" / "history_topics.sqlite"


def available() -> bool:
    """检查历史归类数据库是否可用"""
    return DB_PATH.is_file()


def existing_ids() -> set[int]:
    """
    获取已归类的消息ID集合

    返回:
        消息ID集合，数据库不存在时返回空集

    设计说明:
        用于批量归类前去重，避免重复处理
        幂等操作的基础，确保重跑安全
    """
    if not available():
        return set()
    # sqlite3 连接自带的 with 只提交/回滚事务，不会关闭连接，外层 closing 负责关闭
    with closing(sqlite3.connect(DB_PATH)) as db, db:
        return {row[0] for row in db.execute("SELECT message_id FROM history_topic_classifications")}


def save(rows: list[dict]) -> int:
    """
    保存归类结果到SQLite

    参数:
        rows: 归类记录列表，每条包含message_id、text、labels、asked_at

    返回:
        实际插入的行数（已存在的不计入）

    字段说明:
        - message_id: 消息ID（主键）
        - text: 原始问题文本
        - labels: 主题标签列表（JSON数组）
        - asked_at: 用户提问时间
        - classified_at: 归类时间（自动填充）

    校验规则:
        - message_id不能重复
        - labels必须是非空列表
        - labels中的每个元素必须是TOPIC_NAMES中的合法主题
        - labels不能有重复

    异常:
        ValueError: message_id重复、labels不合法

    设计说明:
        INSERT OR IGNORE确保幂等，重复插入不报错
        返回实际插入数用于统计增量
    """
    if len({row["message_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate history message id")
    for row in rows:
        labels = row["labels"]
        if not isinstance(labels, list) or not labels \
                or any(not isinstance(label, str) or label not in TOPIC_NAMES for label in labels) \
                or len(labels) != len(set(labels)):
            raise ValueError("invalid history classification labels")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    with closing(sqlite3.connect(DB_PATH)) as db, db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS history_topic_classifications (
                message_id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                labels TEXT NOT NULL,
                asked_at TEXT,
                classified_at TEXT NOT NULL
            )
        """)
        before = db.total_changes
        db.executemany(
            "INSERT OR IGNORE INTO history_topic_classifications "
            "(message_id, text, labels, asked_at, classified_at) VALUES (?, ?, ?, ?, ?)",
            [(row["message_id"], row["text"], json.dumps(row["labels"], ensure_ascii=False),
              row.get("asked_at"), stamp) for row in rows],
        )
        return db.total_changes - before


def _rows() -> list[tuple]:
    """
    读取所有归类记录

    返回:
        记录元组列表，按message_id升序

    异常:
        FileNotFoundError: 数据库文件不存在
    """
    if not available():
        raise FileNotFoundError("历史会话尚未归类")
    with closing(sqlite3.connect(DB_PATH)) as db, db:
        return db.execute(
            "SELECT message_id, text, labels, asked_at, classified_at "
            "FROM history_topic_classifications ORDER BY message_id"
        ).fetchall()


def distribution(samples_per_class: int = 3) -> dict:
    """
    统计主题分布

    参数:
        samples_per_class: 每个主题返回的样本数

    返回:
        包含来源、总数、最新归类时间、各主题统计的字典

    统计维度:
        - source: 数据来源标识（"conversation_history"）
        - total: 总消息数
        - latest: 最新归类时间
        - classes: 各主题的计数和样本列表

    样本去重:
        同一文本在同一主题下只保留一次

    设计说明:
        用于验收页面展示归类效果
        samples_per_class限制样本数，避免返回数据过大
    """
    rows = _rows()
    counts = {name: 0 for name in TOPIC_NAMES}
    samples = {name: [] for name in TOPIC_NAMES}
    latest = None
    for _, text, labels_json, _, classified_at in rows:
        latest = max(latest, classified_at) if latest else classified_at
        for label in json.loads(labels_json):
            if label in counts:
                counts[label] += 1
                # 去重且限制数量
                if len(samples[label]) < samples_per_class and text not in samples[label]:
                    samples[label].append(text)
    return {
        "source": "conversation_history",
        "total": len(rows),
        "latest": latest,
        "classes": [{"label": name, "count": counts[name], "samples": samples[name]}
                    for name in TOPIC_NAMES],
    }


def questions(label: str, page: int = 1, size: int = 20) -> dict:
    """
    按主题分页查询问题

    参数:
        label: 主题标签
        page: 页码（从1开始）
        size: 每页大小

    返回:
        包含主题、总数、分页信息、问题列表的字典

    问题字段:
        - question_id: 消息ID
        - labels: 主题标签列表
        - text / raw_question: 原始问题文本
        - normalized: 是否已规范化（历史会话固定为False）
        - source: 数据来源（"conversation_history"）
        - occurrence_count: 出现次数（历史会话固定为1）
        - review_status: 审核状态（历史会话固定为None）
        - asked_at: 提问时间
        - classified_at: 归类时间

    排序规则:
        按message_id倒序，最新的在前

    设计说明:
        字段命名与问题池归类保持一致，确保前端可复用
        页码超出范围时自动调整到最后一页
    """
    # 倒序遍历，提取包含指定标签的记录
    hits = [(mid, text, json.loads(labels_json), asked_at, classified_at)
            for mid, text, labels_json, asked_at, classified_at in reversed(_rows())
            if label in json.loads(labels_json)]
    pages = max(1, -(-len(hits) // size))  # 向上取整
    page = min(page, pages)
    items = [{
        "question_id": mid, "labels": labels, "text": text, "raw_question": text,
        "normalized": False, "source": "conversation_history", "occurrence_count": 1,
        "review_status": None, "asked_at": asked_at, "classified_at": classified_at,
    } for mid, text, labels, asked_at, classified_at in hits[(page - 1) * size:page * size]]
    return {"source": "conversation_history", "label": label, "total": len(hits),
            "page": page, "size": size, "pages": pages, "items": items}
