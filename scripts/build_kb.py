"""将 data/kb 中的演示材料分块后写入 MySQL pending 队列。"""

import asyncio

from app.kb import documents, dualwrite
from app.kb.sources import KB_DIR, SOURCE_TYPES


async def main() -> None:
    total = 0
    for filename, content_type in SOURCE_TYPES.items():
        markdown = (KB_DIR / filename).read_text(encoding="utf-8")
        chunks = documents.build_chunks(markdown, content_type=content_type)
        ids = await dualwrite.write_pending(chunks)
        total += len(ids)
        print(f"{filename}: {len(ids)} chunks")

    print(f"建库完成：核对 {total} 条知识块，已有数据复用，缺失数据补为 pending")


if __name__ == "__main__":
    asyncio.run(main())
