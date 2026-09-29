"""Ch04：统一知识检索入口。"""
from app.config import settings
from app.core import  query_understanding
from app.kb import milvus_client
from app.core import embeddings, rerank
import re
import math
from app.core.coref import entities
from copy import deepcopy
from app.core.confidence import ranked_hits
STRATEGIES = {
    "vector",
    "bm25",
    "hybrid",
    "hybrid_rerank",
}
def split_ranked_hits(
    hits: list[dict],
    min_score: float,
) -> dict[str, list[dict]]:
    """保留精排候选，同时筛选可用于回答的证据。"""
    if (
        isinstance(min_score, bool)
        or not isinstance(min_score, (int, float))
        or not math.isfinite(min_score)
        or not 0 <= min_score <= 1
    ):
        raise ValueError("最低精排分数必须是 0 到 1 之间的有限数值")

    candidates = ranked_hits(hits)

    evidence = [
        deepcopy(hit)
        for hit in candidates
        if hit["rerank_score"] >= min_score
    ]

    return {
        "candidates": candidates,
        "evidence": evidence,
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

async def search_knowledge_detailed(
    query: str,
    strategy: str = "vector",
    top_k: int = 5,
    category: str | None = None,
    *,
    client=None,
    collection: str = milvus_client.COLLECTION,
    rewrite: bool = False,
    split: bool = False,
) -> dict[str, list[dict] | None]:
    """返回可用于回答的证据，以及可用时的精排诊断候选。"""

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

        return split_ranked_hits(
            ranked,
            min_score=settings.rerank_min_score,
        )

    return {
        "candidates": None,
        "evidence": hits,
    }

async def search_knowledge(
    query: str,
    strategy: str = "vector",
    top_k: int = 5,
    category: str | None = None,
    *,
    client=None,
    collection: str = milvus_client.COLLECTION,
    rewrite: bool = False,
    split: bool = False,
) -> list[dict]:
    """保留原接口，只返回可用于回答的证据列表。"""
    result = await search_knowledge_detailed(
        query,
        strategy=strategy,
        top_k=top_k,
        category=category,
        client=client,
        collection=collection,
        rewrite=rewrite,
        split=split,
    )

    return result["evidence"]
async def build_policy_queries(query, order, expand):
    proposed = await expand(query)

    if not isinstance(proposed, list):
        raise ValueError("扩展结果必须是列表")

    queries = [query]
    allowed_entities = set(entities(query))

    if isinstance(order, dict) and order.get("order_id"):
        allowed_entities.add(order["order_id"])

    for item in proposed:
        if not isinstance(item, str):
            continue

        item = item.strip()

        if not item or len(item) > 200:
            continue

        if item in queries:
            continue

        if not set(entities(item)) <= allowed_entities:
            continue

        queries.append(item)

        if len(queries) == 3:
            break

    return queries

async def retrieve_policy(query, order, expand, search):
    queries = await build_policy_queries(query, order, expand)

    merged = {}
    for current_query in queries:
        hits = await search(current_query)

        if not isinstance(hits, list):
            continue

        for hit in hits:
            if not isinstance(hit, dict):
                continue

            hit_id = hit.get("id")
            score = hit.get("rerank_score")

            if (
                isinstance(hit_id, bool)
                or not isinstance(hit_id, (int, str))
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0.3 <= score <= 1
                or not isinstance(hit.get("answer"), str)
                or not hit["answer"].strip()
                or not isinstance(hit.get("section_path"), str)
                or not hit["section_path"].strip()
            ):
                continue

            if (
                hit_id not in merged
                or score > merged[hit_id]["rerank_score"]
            ):
                merged[hit_id] = dict(hit)

    valid_hits = sorted(
        merged.values(),
        key=lambda hit: (-hit["rerank_score"], str(hit["id"])),
    )[:5]

    citations = [
        {**hit, "n": index}
        for index, hit in enumerate(valid_hits, start=1)
    ]

    return queries, citations
async def retrieve_policy_detailed(
    query,
    order,
    expand,
    search,
    rerank_all,
):
    queries = await build_policy_queries(query, order, expand)
    merged = {}

    for current_query in queries:
        result = await search(current_query)

        if not isinstance(result, dict):
            raise ValueError("详细政策检索结果必须是字典")

        candidates = result.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("政策检索需要精排候选列表")

        for hit in ranked_hits(candidates):
            question = hit.get("question", "")
            answer = hit.get("answer")
            section_path = hit.get("section_path")

            if (
                not isinstance(question, str)
                or not isinstance(answer, str)
                or not answer.strip()
                or not isinstance(section_path, str)
                or not section_path.strip()
            ):
                raise ValueError("政策候选缺少有效正文或来源")

            candidate = {
                "id": hit["id"],
                "question": question,
                "answer": answer,
                "section_path": section_path,
            }

            previous = merged.get(hit["id"])
            if previous is not None and previous != candidate:
                raise ValueError("同一知识块 ID 对应不同内容")

            merged[hit["id"]] = candidate

    if not merged:
        return queries, {
            "candidates": [],
            "evidence": [],
        }

    ranked = await rerank_all(
        query,
        list(merged.values()),
        5,
    )

    return queries, split_ranked_hits(
        ranked,
        min_score=settings.rerank_min_score,
    )