"""微调 历史会话归类的隔离存储；不修改业务 MySQL 表。"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.taxonomy import TOPIC_NAMES


DB_PATH = Path(__file__).resolve().parents[2] / "data" / "finetune" / "history_topics.sqlite"


def available() -> bool:
    return DB_PATH.is_file()


def existing_ids() -> set[int]:
    if not available():
        return set()
    with sqlite3.connect(DB_PATH) as db:
        return {row[0] for row in db.execute("SELECT message_id FROM history_topic_classifications")}


def save(rows: list[dict]) -> int:
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
    with sqlite3.connect(DB_PATH) as db:
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
    if not available():
        raise FileNotFoundError("历史会话尚未归类")
    with sqlite3.connect(DB_PATH) as db:
        return db.execute(
            "SELECT message_id, text, labels, asked_at, classified_at "
            "FROM history_topic_classifications ORDER BY message_id"
        ).fetchall()


def distribution(samples_per_class: int = 3) -> dict:
    rows = _rows()
    counts = {name: 0 for name in TOPIC_NAMES}
    samples = {name: [] for name in TOPIC_NAMES}
    latest = None
    for _, text, labels_json, _, classified_at in rows:
        latest = max(latest, classified_at) if latest else classified_at
        for label in json.loads(labels_json):
            if label in counts:
                counts[label] += 1
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
    hits = [(mid, text, json.loads(labels_json), asked_at, classified_at)
            for mid, text, labels_json, asked_at, classified_at in reversed(_rows())
            if label in json.loads(labels_json)]
    pages = max(1, -(-len(hits) // size))
    page = min(page, pages)
    items = [{
        "question_id": mid, "labels": labels, "text": text, "raw_question": text,
        "normalized": False, "source": "conversation_history", "occurrence_count": 1,
        "review_status": None, "asked_at": asked_at, "classified_at": classified_at,
    } for mid, text, labels, asked_at, classified_at in hits[(page - 1) * size:page * size]]
    return {"source": "conversation_history", "label": label, "total": len(hits),
            "page": page, "size": size, "pages": pages, "items": items}
