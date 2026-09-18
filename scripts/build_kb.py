"""将 data/kb 中的演示材料分块后写入 MySQL pending 队列。"""

import asyncio

from app.db import repository
from app.kb import documents, dualwrite
from app.kb.sources import KB_DIR, SOURCE_TYPES


async def main() -> None:
    existing = await repository.count_chunks_by_content_types(
        set(SOURCE_TYPES.values())
    )
    if existing:
        print(f"已存在 {existing} 条知识块，为避免重复，本次跳过。")
        return

    total = 0
    for filename, content_type in SOURCE_TYPES.items():
        markdown = (KB_DIR / filename).read_text(encoding="utf-8")
        chunks = documents.build_chunks(markdown, content_type=content_type)
        ids = await dualwrite.write_pending(chunks)
        total += len(ids)
        print(f"{filename}: {len(ids)} chunks")

    print(f"建库完成：{total} 条 pending 知识块")


if __name__ == "__main__":
    asyncio.run(main())
