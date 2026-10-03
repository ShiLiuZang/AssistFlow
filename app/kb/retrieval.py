"""
知识检索模块
提供统一的知识库检索入口，支持多种检索策略（向量、BM25、混合）
负责协调查询理解、向量化、召回、重排序等环节
是 RAG 系统的核心检索链路，为对话生成提供高质量证据
"""
from app.config import settings
from app.core import query_understanding
from app.kb import milvus_client
from app.core import embeddings
from app.kb import rerank
import asyncio
import re
import math
from app.core.coref import entities
from copy import deepcopy
from app.core.confidence import ranked_hits
# 支持的检索策略集合：纯向量、纯 BM25、混合召回、混合+重排序
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
    """
    拆分精排结果为候选集和证据集

    参数:
        hits: 检索返回的知识片段列表
        min_score: 证据过滤的最低重排序分数阈值（0-1之间）

    返回:
        包含两个列表的字典：
        - candidates: 所有精排后的候选（用于诊断和评估）
        - evidence: 分数达标的高质量证据（用于生成回答）

    设计原因:
        将诊断数据和生成数据分离，candidates 保留完整排序结果供调试，
        evidence 只包含可信度足够高的片段供 LLM 使用，避免低质量信息干扰
    """
    # 验证分数阈值合法性，防止配置错误导致过滤异常
    if (
        isinstance(min_score, bool)
        or not isinstance(min_score, (int, float))
        or not math.isfinite(min_score)
        or not 0 <= min_score <= 1
    ):
        raise ValueError("最低精排分数必须是 0 到 1 之间的有限数值")

    # 按重排序分数降序排列所有候选
    candidates = ranked_hits(hits)

    # 筛选出分数达标的证据，深拷贝避免后续修改影响候选列表
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
    """
    将查询语句按标点符号拆分成多个子句

    参数:
        query: 用户输入的查询语句

    返回:
        拆分后的子句列表，每个子句至少4个字符
        如果无法有效拆分（只有1个子句），返回原查询

    设计原因:
        复杂查询可能包含多个语义单元，分别检索每个子句可以提高召回率
        例如"退货政策是什么，运费谁承担"可拆分为两个独立问题分别检索
    """
    # 按常见中英文标点符号拆分，过滤掉过短的片段（少于4字符可能是噪音）
    parts = [
        part.strip()
        for part in re.split(r"[,，;；?？。]", query)
        if len(part.strip()) >= 4
    ]

    # 只有拆分出多个有效子句时才返回拆分结果，否则保持原查询完整性
    return parts if len(parts) > 1 else [query]

def merge_round_robin(groups: list[list[dict]]) -> list[dict]:
    """
    轮询式合并多组检索结果，保证各子查询结果均衡混合

    参数:
        groups: 多组检索结果列表，每组是一个知识片段列表

    返回:
        合并后的结果列表，按知识片段 ID 去重

    算法逻辑:
        从每组的第1个结果开始轮流取，再取每组第2个，以此类推
        这样可以避免某个子查询的结果淹没其他查询的结果
        同时通过 ID 去重确保同一片段不会重复出现
    """
    result = []
    seen = set()
    # 找出最长的结果列表长度，作为轮询的轮次上限
    max_length = max(
        (len(hits) for hits in groups),
        default=0,
    )
    # 按位置索引轮询，每轮从各组中取出相同位置的结果
    for index in range(max_length):
        for hits in groups:
            # 如果当前组在此位置没有结果，跳过
            if index >= len(hits):
                continue

            hit = hits[index]
            hit_id = hit["id"]
            # 已经见过的片段不再添加（按 ID 去重）
            if hit_id in seen:
                continue
            result.append(hit)
            seen.add(hit_id)
    return result

async def gather_or_cancel(*awaitables):
    """并行执行并按顺序返回结果；任一出错时取消其余的并抛出该错误（与串行执行时一样只得到一个错误）。"""
    tasks = [asyncio.ensure_future(item) for item in awaitables]
    if not tasks:
        return []
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in tasks:
            if task.done() and not task.cancelled() and task.exception() is not None:
                raise task.exception()
        return [task.result() for task in tasks]
    finally:
        pending = [task for task in tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


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
    """
    知识库检索的核心函数，返回详细的检索结果

    参数:
        query: 用户查询语句
        strategy: 检索策略，支持 vector/bm25/hybrid/hybrid_rerank
        top_k: 返回的最终结果数量
        category: 可选的知识分类过滤条件
        client: 可选的 Milvus 客户端实例（用于测试或多客户端场景）
        collection: Milvus 集合名称
        rewrite: 是否启用查询改写（查询理解模块）
        split: 是否启用查询拆分（多子句独立检索）

    返回:
        字典包含：
        - candidates: 精排后的所有候选（仅在 hybrid_rerank 策略下有值）
        - evidence: 可用于回答的高质量证据列表

    检索流程:
        1. 查询理解：改写和扩展原始查询（可选）
        2. 查询拆分：将复杂查询拆分为多个子句（可选）
        3. 向量化：将查询转换为向量表示（非 BM25 策略）
        4. 召回：根据策略从 Milvus 检索候选集
        5. 合并：轮询式合并多个子查询的结果
        6. 重排序：使用精排模型重新排序（仅 hybrid_rerank 策略）
        7. 过滤：按分数阈值筛选出高质量证据
    """
    # 验证检索策略合法性
    if strategy not in STRATEGIES:
        raise ValueError(f"不支持的检索策略：{strategy}")
    if top_k < 1:
        raise ValueError("top_k 必须为正数")

    # 第一步：查询理解（改写和扩展）
    if rewrite:
        understood = await query_understanding.understand(query)
    else:
        # 不启用查询理解时，使用原始查询
        understood = {
            "standard": query,
            "expanded": [],
        }

    standard = understood["standard"]
    # 第二步：查询拆分（将复杂查询拆分为多个子句）
    clauses = split_clauses(standard) if split else [standard]

    # 确定召回数量：hybrid_rerank 策略需要更大的召回集用于后续精排
    recall = max(top_k, settings.recall_top_k)
    candidate_k = (
        recall
        if strategy == "hybrid_rerank"
        else top_k
    )

    groups = []

    # 第三步：对每个子句独立检索
    for clause in clauses:
        # 构建词法检索查询：原子句 + 扩展词
        lexical = " ".join([
            clause,
            *understood["expanded"],
        ])

        # 第四步：向量化查询（BM25 策略不需要向量）
        vector = None
        if strategy != "bm25":
            vector = await embeddings.embed_query(clause)
            # 验证向量维度匹配，防止模型配置不一致
            if len(vector) != milvus_client.DIM:
                raise ValueError("查询向量维度不匹配")

        # 定义检索函数，根据策略选择不同的检索方法
        def search():
            # 获取或使用指定的 Milvus 客户端
            milvus = (
                client
                if client is not None
                else milvus_client.get_client()
            )
            # 确保目标集合存在
            milvus_client.ensure_collection(
                milvus,
                collection=collection,
            )

            # 纯向量检索：基于语义相似度
            if strategy == "vector":
                return milvus_client.dense_search(
                    milvus,
                    vector,
                    candidate_k,
                    collection=collection,
                    category=category,
                )

            # 纯 BM25 检索：基于关键词匹配
            if strategy == "bm25":
                return milvus_client.bm25_search(
                    milvus,
                    lexical,
                    candidate_k,
                    collection=collection,
                    category=category,
                )

            # 混合检索：结合向量和 BM25，互补优势
            return milvus_client.hybrid_search(
                milvus,
                vector,
                lexical,
                candidate_k,
                collection=collection,
                category=category,
                recall=recall,
            )

        # 异步执行检索（Milvus 是同步的，需要包装为异步）
        group = await milvus_client.acall(search)
        groups.append(group)

    # 第五步：合并多个子查询的结果，轮询式取样保证均衡性
    hits = merge_round_robin(groups)[:candidate_k]

    # 第六步：精排序（仅 hybrid_rerank 策略）
    if strategy == "hybrid_rerank":
        # 使用跨编码器重排序模型计算更精确的相关性分数
        ranked = await rerank.rerank_hits(
            standard,
            hits,
            top_k,
        )

        # 拆分为候选集和证据集，按分数阈值过滤证据
        return split_ranked_hits(
            ranked,
            min_score=settings.rerank_min_score,
        )

    # 其他策略直接返回召回结果作为证据，不提供候选集
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
    """
    简化版检索接口，仅返回证据列表

    参数:
        与 search_knowledge_detailed 相同

    返回:
        可用于回答的证据列表（知识片段）

    设计原因:
        保持向后兼容，为不需要诊断信息的调用方提供简洁接口
        内部调用 search_knowledge_detailed 并提取 evidence 字段
    """
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
    """
    构建政策类查询的扩展查询列表

    参数:
        query: 用户原始查询
        order: 订单信息字典（可能包含 order_id）
        expand: 查询扩展函数（通常是 LLM 生成相关问题）

    返回:
        扩展后的查询列表（最多3个），包含原查询和相关衍生查询

    安全机制:
        1. 实体约束：扩展查询中的实体必须来自原查询或订单信息
        2. 长度限制：扩展查询不超过200字符，防止生成过长无效查询
        3. 去重：确保不会重复添加相同的查询

    设计原因:
        政策类查询往往有多种表述方式，通过扩展可以提高召回率
        但需要严格控制扩展范围，避免偏离原始意图或引入无关查询
    """
    # 调用扩展函数生成候选查询
    proposed = await expand(query)

    if not isinstance(proposed, list):
        raise ValueError("扩展结果必须是列表")

    # 初始查询列表包含原查询
    queries = [query]
    # 提取原查询中的实体（人名、地名、订单号等）
    allowed_entities = set(entities(query))

    # 如果有订单信息，允许订单号出现在扩展查询中
    if isinstance(order, dict) and order.get("order_id"):
        allowed_entities.add(order["order_id"])

    # 遍历候选扩展查询
    for item in proposed:
        if not isinstance(item, str):
            continue

        item = item.strip()

        # 过滤过短或过长的扩展查询
        if not item or len(item) > 200:
            continue

        # 去重：已存在的查询不再添加
        if item in queries:
            continue

        # 实体约束：扩展查询的实体必须是原查询或订单的子集
        # 这样可以防止扩展查询引入无关的实体，偏离原始意图
        if not set(entities(item)) <= allowed_entities:
            continue

        queries.append(item)

        # 最多保留3个查询（原查询 + 2个扩展）
        if len(queries) == 3:
            break

    return queries

async def retrieve_policy(query, order, expand, search):
    """
    政策类知识检索（简化版）

    参数:
        query: 用户查询
        order: 订单信息
        expand: 查询扩展函数
        search: 检索函数（执行单次检索）

    返回:
        元组 (queries, citations)
        - queries: 实际使用的查询列表
        - citations: 带引用编号的证据列表（最多5条）

    检索流程:
        1. 扩展查询：生成多个相关查询
        2. 分别检索：对每个查询独立检索
        3. 合并去重：按 ID 去重，保留最高分
        4. 排序截断：按分数排序，取前5条
        5. 添加引用：为每条证据添加编号

    质量保障:
        - 分数阈值：只保留 rerank_score >= 0.3 的结果
        - 内容验证：必须有非空的 answer 和 section_path
        - 去重策略：同一知识片段保留最高分的那次检索结果
    """
    # 构建扩展查询列表
    queries = await build_policy_queries(query, order, expand)

    # 用于合并和去重的字典，key 是知识片段 ID
    merged = {}
    for current_query in queries:
        # 执行单次检索
        hits = await search(current_query)

        if not isinstance(hits, list):
            continue

        for hit in hits:
            if not isinstance(hit, dict):
                continue

            hit_id = hit.get("id")
            score = hit.get("rerank_score")

            # 验证结果的有效性和质量
            if (
                isinstance(hit_id, bool)
                or not isinstance(hit_id, (int, str))
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0.3 <= score <= 1  # 分数阈值：至少0.3
                or not isinstance(hit.get("answer"), str)
                or not hit["answer"].strip()  # 必须有非空答案
                or not isinstance(hit.get("section_path"), str)
                or not hit["section_path"].strip()  # 必须有非空来源
            ):
                continue

            # 去重：保留同一片段的最高分结果
            if (
                hit_id not in merged
                or score > merged[hit_id]["rerank_score"]
            ):
                merged[hit_id] = dict(hit)

    # 按分数降序排序，取前5条
    valid_hits = sorted(
        merged.values(),
        key=lambda hit: (-hit["rerank_score"], str(hit["id"])),
    )[:5]

    # 添加引用编号（从1开始）
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
    """
    政策类知识检索（详细版）

    参数:
        query: 用户查询
        order: 订单信息
        expand: 查询扩展函数
        search: 检索函数（返回详细结果包含 candidates）
        rerank_all: 全局重排序函数（对所有候选重新排序）

    返回:
        元组 (queries, split_result)
        - queries: 实际使用的查询列表
        - split_result: 包含 candidates 和 evidence 的字典

    与 retrieve_policy 的区别:
        1. 使用详细版检索接口，获取所有候选而非仅证据
        2. 收集所有候选后进行全局重排序，而非使用单次检索的分数
        3. 返回完整的候选集和证据集，用于诊断和评估

    设计原因:
        简化版对每个查询独立排序可能导致不一致，详细版通过全局重排序
        确保所有候选在同一标准下比较，提供更准确的排序结果
    """
    # 原问题的检索不依赖扩展结果：和扩展（一次模型调用）同时开始，扩展出的查询再并行检索
    first = asyncio.ensure_future(search(query))
    try:
        queries = await build_policy_queries(query, order, expand)
        results = await gather_or_cancel(first, *(search(item) for item in queries[1:]))
    except BaseException:
        first.cancel()
        raise
    # 用于收集所有候选的字典
    merged = {}

    # 按查询顺序合并检索结果
    for result in results:

        if not isinstance(result, dict):
            raise ValueError("详细政策检索结果必须是字典")

        candidates = result.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("政策检索需要精排候选列表")

        # 遍历候选，提取关键字段
        for hit in ranked_hits(candidates):
            question = hit.get("question", "")
            answer = hit.get("answer")
            section_path = hit.get("section_path")

            # 验证候选的必要字段
            if (
                not isinstance(question, str)
                or not isinstance(answer, str)
                or not answer.strip()
                or not isinstance(section_path, str)
                or not section_path.strip()
            ):
                raise ValueError("政策候选缺少有效正文或来源")

            # 构建标准化的候选对象
            candidate = {
                "id": hit["id"],
                "question": question,
                "answer": answer,
                "section_path": section_path,
            }

            # 检查同一 ID 的一致性（防止数据错误）
            previous = merged.get(hit["id"])
            if previous is not None and previous != candidate:
                raise ValueError("同一知识块 ID 对应不同内容")

            merged[hit["id"]] = candidate

    # 如果没有任何候选，返回空结果
    if not merged:
        return queries, {
            "candidates": [],
            "evidence": [],
        }

    # 对所有收集到的候选进行全局重排序
    ranked = await rerank_all(
        query,
        list(merged.values()),
        5,
    )

    # 拆分为候选集和证据集
    return queries, split_ranked_hits(
        ranked,
        min_score=settings.rerank_min_score,
    )