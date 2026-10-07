"""基础 Dense 检索工具。"""
from langchain_core.tools import tool
from app.core.embeddings import embed_query
from app.kb import milvus_client


@tool
async def search_knowledge(query: str) -> dict:
    """回答退换货、运费、会员、商品规格前，检索知识原文；无证据不能猜测。"""
    vector = await embed_query(query)
    if len(vector) != milvus_client.DIM:
        raise ValueError("问题向量维度不匹配")
    def search():
        client = milvus_client.get_client()
        milvus_client.ensure_collection(client)
        return milvus_client.dense_search(client, vector, top_k=5)
    hits = await milvus_client.acall(search)
    return {"evidence": hits, "instruction": "只使用与问题相关的原文；不相关或不足时明确说无法确认。"}
