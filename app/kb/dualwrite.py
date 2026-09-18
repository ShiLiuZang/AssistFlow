"""Ch03：协调 MySQL 原文状态与 Milvus 向量写入。"""

from app.core import embeddings
from app.kb import milvus_client
from app.db import repository
from app.kb.documents import Chunk
async def write_pending(
    chunks: list[Chunk],
) -> list[int]:
    ids: list[int] = []

    for chunk in chunks:
        chunk_id = await repository.insert_knowledge_chunk(
            chunk.category,
            chunk.questions,
            chunk.answer,
            section_path=chunk.section_path,
            content_type=chunk.content_type,
            is_key_clause=chunk.is_key_clause,
        )
        ids.append(chunk_id)

    for index, chunk_id in enumerate(ids):
        prev_id = ids[index - 1] if index > 0 else None

        next_id = (
            ids[index + 1]
            if index < len(ids) - 1
            else None
        )

        await repository.set_chunk_neighbors(
            chunk_id,
            prev_id,
            next_id,
        )

    return ids
def _batches(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]
async def vectorize_pending(
    client=None,
    batch_size: int = 64,
    collection: str = milvus_client.COLLECTION,
) -> int:
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