"""候选队列命令；mine 调模型，approve 入 MySQL pending，不自动向量化。"""
import argparse
import asyncio
import json
from pathlib import Path
from app.kb.mining import mine_dialogue, publish_approved, stage_candidates


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["mine", "list", "approve", "reject"])
    parser.add_argument("--queue", type=Path, default=Path("data/review/queue.json"))
    parser.add_argument("--input", type=Path, help="已脱敏的对话 JSON 数组")
    parser.add_argument("--index", type=int)
    parser.add_argument("--reviewer")
    args = parser.parse_args()
    items = json.loads(args.queue.read_text(encoding="utf-8")) if args.queue.exists() else []
    if args.action == "list":
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return
    if args.action == "mine":
        if not args.input:
            parser.error("mine 需要 --input 脱敏对话文件")
        items = stage_candidates(items, await mine_dialogue(json.loads(args.input.read_text(encoding="utf-8"))))
    else:
        if args.index is None or not 0 <= args.index < len(items) or not args.reviewer:
            parser.error("审核需要有效 --index 和 --reviewer")
        item = dict(items[args.index])
        item.update(status="approved" if args.action == "approve" else "rejected", reviewer=args.reviewer)
        if args.action == "approve":
            item["chunk_ids"] = await publish_approved(item)
        items[args.index] = item
    args.queue.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.queue.with_suffix(".tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(args.queue)
    print(f"已保存 {len(items)} 条候选：{args.queue}")


if __name__ == "__main__":
    asyncio.run(main())
