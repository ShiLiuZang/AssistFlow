"""
知识库构建脚本

将 data/kb 中的演示材料分块后写入 MySQL pending 队列
核心功能：解析 Markdown 文档、生成知识块、写入数据库
使用场景：知识库初始化和更新
"""

import asyncio

from app.kb import documents, dualwrite
from app.kb.sources import KB_DIR, SOURCE_TYPES


async def main() -> None:
    """
    主函数：遍历所有知识库源文件并构建知识块

    处理流程:
        1. 遍历SOURCE_TYPES中定义的所有文件
        2. 读取Markdown文件内容
        3. 按content_type分块
        4. 写入数据库pending队列
        5. 统计并输出结果

    设计说明:
        - 幂等性：已有数据复用，只补充缺失数据
        - 支持增量更新：重复运行不会重复插入
    """
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
