"""按审核项定向发布一个知识块，可用同一 ID 恢复中断的写入。"""

import logging

from app.core import embeddings
from app.core.trusted_sources import validate_review_source
from app.db import repository
from app.kb import milvus_client
from app.kb.sources import SOURCE_TYPES


logger = logging.getLogger(__name__)


class MilvusReviewIndex:
    def __init__(self, client=None, collection: str | None = None) -> None:
        self.client = client
        self.collection = collection or milvus_client.COLLECTION

    async def upsert(self, chunk: dict) -> None:
        text = f"{chunk['category']}\n{chunk['question']}\n{chunk['answer']}"
        vectors = await embeddings.embed_texts([text])
        if len(vectors) != 1 or len(vectors[0]) != milvus_client.DIM:
            raise ValueError("审核知识块嵌入向量无效")
        row = {
            "id": chunk["id"],
            "dense": vectors[0],
            "question": chunk["question"],
            "answer": chunk["answer"],
            "section_path": chunk["section_path"] or "",
            "content_type": chunk["content_type"] or "",
            "category": chunk["category"],
            "text": text,
        }

        def write() -> None:
            client = self.client or milvus_client.get_client()
            milvus_client.ensure_collection(client, collection=self.collection)
            milvus_client.upsert_vectors(client, [row], collection=self.collection)
            milvus_client.flush(client, collection=self.collection)

        await milvus_client.acall(write)

    async def visible(self, chunk: dict) -> bool:
        def read() -> bool:
            client = self.client or milvus_client.get_client()
            milvus_client.ensure_collection(client, collection=self.collection)
            rows = client.query(
                collection_name=self.collection,
                filter=f"id == {chunk['id']}",
                output_fields=["id", "question", "answer"],
            )
            return any(
                row.get("id") == chunk["id"]
                and row.get("question") == chunk["question"]
                and row.get("answer") == chunk["answer"]
                for row in rows
            )

        return await milvus_client.acall(read)


async def publish_review(review_id: int, index=None) -> dict:
    """SQL 准备、向量 upsert、可见性确认、SQL 完成四步可重放。"""
    review = await repository.get_review_detail(review_id)
    if review is None:
        raise LookupError("review not found")
    if review["status"] not in {"publishing", "approved"}:
        raise ValueError("审核项尚未核准")

    try:
        current_digest = validate_review_source(
            review["question"], review["answer"], review["source_ref"],
        )
        if current_digest != review["source_digest"]:
            raise ValueError("可信材料版本已变化，停止发布")
        chunk = await repository.prepare_review_chunk(
            review_id,
            SOURCE_TYPES[review["source_ref"]],
        )
        target = index or MilvusReviewIndex()
        await target.upsert(chunk)
        if not await target.visible(chunk):
            raise RuntimeError("审核知识块尚未在向量库可见")
        result = await repository.finish_review_publish(review_id, chunk["id"])
        return {**result, "chunk_id": chunk["id"]}
    except Exception as exc:
        code = type(exc).__name__
        try:
            await repository.note_review_publish_error(review_id, code)
        except Exception:
            logger.exception("failed to record publish error for review %s", review_id)
        raise
