"""Ch04：统一知识检索入口。"""
from app.config import settings
from app.core import  query_understanding
from app.kb import milvus_client
from app.core import embeddings, rerank
import re
STRATEGIES = {
    "vector",
    "bm25",
    "hybrid",
    "hybrid_rerank",
}
def split_clauses(query: str) -> list[str]:
    """按标点拆分问题，无法有效拆分时保留原问题。"""
    parts = [
        part.strip()
        for part in re.split(r"[,，;；?？。]", query)
        if len(part.strip()) >= 4
    ]

    return parts if len(parts) > 1 else [query]
def merge_round_robin(groups: list[list[dict]]) -> list[dict]:
    """交替合并多组检索结果，按知识片段 ID 去重。"""
    result = []
    seen = set()
    max_length = max(
        (len(hits) for hits in groups),
        default=0,
    )
    for index in range(max_length):
        for hits in groups:
            if index >= len(hits):
                continue

            hit = hits[index]
            hit_id = hit["id"]
            if hit_id in seen:
                continue
            result.append(hit)
            seen.add(hit_id)
    return result

async def search_knowledge(
    query:str,
    strategy:str="vector",
    top_k:int=5,
    category: str | None = None,
    *,
    client=None,
    collection: str = milvus_client.COLLECTION,
    rewrite: bool = False,
    split: bool = False,

)->list[dict]:
    """根据策略检索知识，返回统一的命中结果。"""
    if strategy not in STRATEGIES:
        raise ValueError(f"不支持的检索策略：{strategy}")
    if top_k < 1:
        raise ValueError("top_k 必须为正数")

    # 新增：选择原问题或改写后的问题。
    if rewrite:
        understood = await query_understanding.understand(query)
    else:
        understood = {
            "standard": query,
            "expanded": [],
        }

    standard = understood["standard"]
    clauses = split_clauses(standard) if split else [standard]

    recall = max(top_k, settings.recall_top_k)
    candidate_k = (
        recall
        if strategy == "hybrid_rerank"
        else top_k
    )

    groups = []

    for clause in clauses:
        lexical = " ".join([
            clause,
            *understood["expanded"],
        ])

        vector = None
        if strategy != "bm25":
            vector = await embeddings.embed_query(clause)
            if len(vector) != milvus_client.DIM:
                raise ValueError("查询向量维度不匹配")

        def search():
            milvus = (
                client
                if client is not None
                else milvus_client.get_client()
            )
            milvus_client.ensure_collection(
                milvus,
                collection=collection,
            )

            if strategy == "vector":
                return milvus_client.dense_search(
                    milvus,
                    vector,
                    candidate_k,
                    collection=collection,
                    category=category,
                )

            if strategy == "bm25":
                return milvus_client.bm25_search(
                    milvus,
                    lexical,
                    candidate_k,
                    collection=collection,
                    category=category,
                )

            return milvus_client.hybrid_search(
                milvus,
                vector,
                lexical,
                candidate_k,
                collection=collection,
                category=category,
                recall=recall,
            )

        group = await milvus_client.acall(search)
        groups.append(group)

    hits = merge_round_robin(groups)[:candidate_k]

    if strategy == "hybrid_rerank":
        ranked = await rerank.rerank_hits(
            standard,
            hits,
            top_k,
        )

        return [
            hit
            for hit in ranked
            if hit["rerank_score"] >= settings.rerank_min_score
        ]

    return hits