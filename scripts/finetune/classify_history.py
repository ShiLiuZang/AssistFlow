"""用配置的分类服务归类历史用户提问，结果写入隔离 SQLite。"""

import asyncio
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import httpx

from app.config import settings
from app.core import history_topics
from app.db import topic_repo
from scripts.finetune.corpus_lib import dedupe, desensitize


SERVICE = settings.classifier_url.rstrip("/")
REPORT = Path("data/finetune/reports/history_classify_run.json")


async def main() -> None:
    source = await topic_repo.list_history_user_texts()
    rows = dedupe([{"message_id": row["message_id"],
                    "text": desensitize(row["text"]),
                    "asked_at": row["asked_at"]}
                   for row in source])
    existing = await asyncio.to_thread(history_topics.existing_ids)
    pending = [row for row in rows if row["message_id"] not in existing]
    if pending:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{SERVICE}/classify",
                                         json={"texts": [row["text"] for row in pending]})
            response.raise_for_status()
            results = response.json()["results"]
        classified = [{**row, "labels": result["labels"]}
                      for row, result in zip(pending, results, strict=True)]
        written = await asyncio.to_thread(history_topics.save, classified)
    else:
        written = 0
    dist = await asyncio.to_thread(history_topics.distribution)
    counts = Counter({item["label"]: item["count"] for item in dist["classes"]})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "conversation_history", "status": "done" if written else "empty",
        "pending": len(pending), "written": written, "total": dist["total"],
        "counts": dict(counts),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"历史用户提问去重 {len(rows)} 条，本次归类 {written} 条，隔离库共 {dist['total']} 条")


if __name__ == "__main__":
    asyncio.run(main())
