"""Ch03：协调 MySQL 原文状态与 Milvus 向量写入。"""

from app.core import embeddings
from app.kb import milvus_client
from app.db import repository
from app.kb.documents import Chunk
async def write_pending(
    chunks: list[Chunk],
) -> list[int]:
    return await repository.ensure_knowledge_chunks(chunks)
def _batches(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]
async def vectorize_pending(
    client=None,
    batch_size: int = 64,
    collection: str = milvus_client.COLLECTION,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size 必须为正数")
    pending = await repository.list_pending_chunks()
    done = 0

    for batch in _batches(pending, batch_size):
        texts = [
            f"{row.category}\n"
            f"{row.questions}\n"
            f"{row.answer}"
            for row in batch
        ]

        vectors = await embeddings.embed_texts(texts)

        if len(vectors) != len(batch):
            raise ValueError(
                "嵌入结果数量与知识块数量不一致"
            )

        if any(
            len(vector) != milvus_client.DIM
            for vector in vectors
        ):
            raise ValueError(
                "嵌入向量维度不匹配"
            )

        rows = [
            {
                "id": row.id,
                "dense": vector,
                "question": row.questions,
                "answer": row.answer,
                "section_path": row.section_path or "",
                "content_type": row.content_type or "",
                "category": row.category or "",
            }
            for row, vector in zip(batch, vectors)
        ]

        def work_upsert(rows=rows):
            milvus = client or milvus_client.get_client()

            milvus_client.ensure_collection(
                milvus,
                collection=collection,
            )

            milvus_client.upsert_vectors(
                milvus,
                rows,
                collection=collection,
            )

            milvus_client.flush(
                milvus,
                collection=collection,
            )

        await milvus_client.acall(work_upsert)

        for row in batch:
            await repository.mark_chunk_vectorized(
                row.id,
                str(row.id),
            )

        done += len(batch)

    return done
