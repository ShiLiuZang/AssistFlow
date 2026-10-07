"""
知识库验证脚本
检查MySQL中的向量化状态统计、Milvus中的记录数量
并执行一次演示检索，验证向量检索链路是否正常
"""
import asyncio

from sqlalchemy import func, select

from app.core.embeddings import embed_query
from app.db.database import SessionLocal
from app.db.models import KnowledgeChunk
from app.kb import milvus_client


async def main() -> None:
    """验证知识库双写状态和检索功能"""
    async with SessionLocal() as session:
        counts = await session.execute(
            select(
                KnowledgeChunk.vectorize_status,
                func.count(KnowledgeChunk.id),
            ).group_by(KnowledgeChunk.vectorize_status)
        )
        print("mysql_status=", dict(counts.all()))

    client = milvus_client.get_client()
    milvus_client.ensure_collection(client)
    print("milvus_count=", milvus_client.count(client))

    query = "退货寄回去谁出钱"
    vector = await embed_query(query)
    hits = milvus_client.dense_search(client, vector, top_k=3)
    print("query=", query)
    for hit in hits:
        print(
            hit["id"],
            hit["score"],
            hit["section_path"],
            hit["answer"][:80],
        )


if __name__ == "__main__":
    asyncio.run(main())
