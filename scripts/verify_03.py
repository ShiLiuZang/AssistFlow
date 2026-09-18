import asyncio

from sqlalchemy import func, select

from app.core.embeddings import embed_query
from app.db.database import SessionLocal
from app.db.models import KnowledgeChunk
from app.kb import milvus_client


async def main() -> None:
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
