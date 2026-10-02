"""从最近对话生成可信候选，复用原挖掘函数，只写暂存区。"""
import asyncio
import hashlib
import json
import re

from sqlalchemy import select, func

from app.db.database import SessionLocal, engine
from app.db.models import Message, KnowledgeChunk, QaExtractionStaging
from app.kb.mining import mine_dialogue, validate_candidate
from app.kb.dedup import normalize_question
from scripts.finetune.corpus_lib import desensitize


def sanitize_dialogue(rows) -> list[dict]:
    result, remaining = [], 12000
    for row in rows:
        content = re.sub(r"ORD-[\w-]+", "[订单号]", desensitize(row.content or ""), flags=re.I)
        content = content[:min(4000, remaining)]
        if content.strip():
            result.append({"role": row.role, "content": content})
            remaining -= len(content)
        if remaining <= 0:
            break
    return result


async def run_mining(session_factory=SessionLocal, miner=mine_dialogue, limit=20) -> dict:
    summary = {"conversations": 0, "kept": 0, "discarded": 0, "unchanged": 0, "failed": 0}
    async with session_factory() as session:
        ids = list(await session.scalars(select(Message.conversation_id).where(
            Message.role == "assistant", Message.content.is_not(None), Message.content != ""
        ).group_by(Message.conversation_id).order_by(func.max(Message.id).desc()).limit(limit)))
    for cid in ids:
        try:
            async with session_factory() as session:
                rows = list(await session.scalars(select(Message).where(
                    Message.conversation_id == cid, Message.role.in_(["user", "assistant"])
                ).order_by(Message.id.desc()).limit(40)))
                dialogue = sanitize_dialogue(reversed(rows))
                if not any(r["role"] == "user" for r in dialogue):
                    continue
                digest = hashlib.sha256(json.dumps(dialogue, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
                batch = f"mine-{cid}-{digest}"
                if await session.scalar(select(QaExtractionStaging.id).where(QaExtractionStaging.batch_no == batch).limit(1)):
                    summary["unchanged"] += 1
                    continue
            candidates = await asyncio.wait_for(miner(dialogue), timeout=90)
            summary["conversations"] += 1
            async with session_factory() as session:
                known = list(await session.scalars(select(KnowledgeChunk.questions)))
                known += list(await session.scalars(select(QaExtractionStaging.question)))
                seen = {normalize_question(q) for q in known if q}
                existing_pairs = set((await session.execute(select(QaExtractionStaging.question, QaExtractionStaging.answer))).all())
                added = {"kept": 0, "discarded": 0}
                for raw in candidates:
                    candidate = validate_candidate(raw)
                    pair = (candidate.question, candidate.quote)
                    if pair in existing_pairs:
                        continue
                    key = normalize_question(candidate.question)
                    status = "discarded" if not key or key in seen else "kept"
                    session.add(QaExtractionStaging(batch_no=batch, source_ref=candidate.source_file,
                        question=candidate.question, answer=candidate.quote, status=status))
                    existing_pairs.add(pair)
                    seen.add(key)
                    added[status] += 1
                await session.commit()
                for key, count in added.items():
                    summary[key] += count
            print(f"会话 #{cid} 已处理：保留 {added['kept']}，去重丢弃 {added['discarded']}", flush=True)
        except Exception as exc:
            summary["failed"] += 1
            # 不把原始对话或模型响应写入作业日志。
            print(f"会话 #{cid} 未完成：{type(exc).__name__}，可在依赖恢复后重跑", flush=True)
    return summary


async def main():
    try:
        result = await run_mining()
        print(json.dumps(result, ensure_ascii=False))
        print("仅生成待审候选，未写正式知识库、未执行向量化。")
        return 1 if result["failed"] else 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
