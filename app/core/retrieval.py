"""Ch04：统一知识检索入口。"""
from app.config import settings
from app.core import embeddings
from app.kb import milvus_client

STRATEGIES={"vector","bm25","hybrid"}

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
            top_k,
            collection=collection,
            category=category,
            recall=max(top_k,settings.recall_top_k),
        )

    return await milvus_client.acall(search)