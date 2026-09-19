"""Ch04：统一知识检索入口。"""
from app.config import settings
    
from app.kb import milvus_client
from app.core import embeddings, rerank

STRATEGIES = {
    "vector",
    "bm25",
    "hybrid",
    "hybrid_rerank",
}


async def search_knowledge(
    query:str,
    strategy:str="vector",
    top_k:int=5,
    category: str | None = None,
    *,
    client=None,
    collection: str = milvus_client.COLLECTION,

)->list[dict]:
    """根据策略检索知识，返回统一的命中结果。"""
    if strategy not in STRATEGIES:
        raise ValueError(f"不支持的检索策略：{strategy}")
    if top_k<1:
        raise ValueError("top_k 必须为正数")
    vector = None

    if strategy !="bm25":
        vector=await    embeddings.embed_query(query)
        if len(vector)!=milvus_client.DIM:
            raise ValueError("查询向量维度不匹配")

    def search():
        recall = max(top_k, settings.recall_top_k)

        candidate_k = (
            recall
            if strategy == "hybrid_rerank"
            else top_k
        )
        milvus=client if client is not None else milvus_client.get_client()
        milvus_client.ensure_collection(
            milvus,
            collection=collection,
        )
        if strategy == "vector":
            return milvus_client.dense_search(
                milvus,
                vector,
                top_k,
                collection=collection,
                category=category,
            )
        if strategy == "bm25":
            return milvus_client.bm25_search(
                milvus,
                query,
                top_k,
                collection=collection,
                category=category,
            )
        return milvus_client.hybrid_search(
            milvus,
            vector,
            query,
            candidate_k,
            collection=collection,
            category=category,
            recall=recall,
        )

    hits = await milvus_client.acall(search)

    if strategy == "hybrid_rerank":
        ranked = await rerank.rerank_hits(
            query,
            hits,
            top_k,
        )

        return [
            hit
            for hit in ranked
            if hit["rerank_score"] >= settings.rerank_min_score
        ]

    return hits