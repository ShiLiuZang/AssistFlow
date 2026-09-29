"""
知识库向量化脚本

运行方式：python -m scripts.vectorize_kb
核心功能：将 pending 状态的知识块向量化并写入 Milvus
失败后重跑只处理 pending 状态的记录，支持断点续传
"""

import asyncio
from app.kb.dualwrite import vectorize_pending


async def main():
    """
    主函数：向量化所有pending状态的知识块

    处理流程:
        1. 查询vectorize_status为pending的知识块
        2. 调用embedding模型生成向量
        3. 写入Milvus向量数据库
        4. 更新MySQL中的状态为done

    设计说明:
        - 幂等性：只处理pending状态，已完成的不重复处理
        - 容错性：失败后重跑可以继续未完成的工作
    """
    count = await vectorize_pending()
    print(f"本次完成向量化：{count} 条")


if __name__ == "__main__":
    asyncio.run(main())
