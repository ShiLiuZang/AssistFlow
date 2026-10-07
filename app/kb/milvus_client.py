# 模块：Milvus向量数据库客户端
# 封装Milvus向量数据库的操作，支持Dense向量、BM25、混合检索
# 管理集合创建、向量插入、检索、结果转换
# 核心职责：提供知识库的向量检索能力，支持语义搜索和关键词匹配

import json
import asyncio
import functools

from concurrent.futures import ThreadPoolExecutor

from pymilvus import (
    DataType,
    Function,
    FunctionType,
    MilvusClient,
    AnnSearchRequest,
    RRFRanker,
)

from app.config import settings


# 集合名称（从配置读取）
COLLECTION = settings.milvus_collection

# 向量维度（与嵌入模型匹配）
DIM = 1024

# 检索时返回的字段列表
_OUTPUT_FIELDS = [
    "question",
    "answer",
    "section_path",
    "content_type",
    "category",
]

# 单线程执行器（pymilvus是同步库，需在线程池中执行）
_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="milvus",
)

# 全局客户端实例
_CLIENT: MilvusClient | None = None

# 已确保存在的集合（避免重复检查）
_ENSURED_COLLECTIONS: set[str] = set()


async def acall(function, *args, **kwargs):
    """
    在线程池中运行同步的pymilvus操作

    参数:
        function: 同步函数
        *args: 位置参数
        **kwargs: 关键字参数

    返回:
        函数执行结果

    设计说明:
        pymilvus是同步库，异步环境中需用线程池执行
        单线程池避免并发访问Milvus的潜在问题
    """
    loop = asyncio.get_running_loop()

    task = functools.partial(
        function,
        *args,
        **kwargs,
    )

    return await loop.run_in_executor(
        _EXECUTOR,
        task,
    )


def get_client(
    uri: str | None = None,
) -> MilvusClient:
    """
    获取Milvus客户端

    参数:
        uri: Milvus连接URI（可选，测试时传入独立URI）

    返回:
        MilvusClient实例

    设计说明:
        uri为None时返回全局单例客户端
        测试时传入独立URI创建临时客户端
        5秒超时确保不阻塞过久
    """
    global _CLIENT

    if uri is not None:
        return MilvusClient(
            uri=uri,
            timeout=5,
        )

    if _CLIENT is None:
        _CLIENT = MilvusClient(
            uri=settings.milvus_uri,
            timeout=5,
        )

    return _CLIENT


def ensure_collection(
    client: MilvusClient,
    collection: str = COLLECTION,
) -> None:
    """
    确保集合存在并已加载

    参数:
        client: Milvus客户端
        collection: 集合名称

    处理逻辑:
        集合存在：校验字段和维度，然后加载
        集合不存在：创建schema、索引，然后加载

    字段定义:
        - id: 主键（knowledge_chunks表的ID）
        - dense: 稠密向量（1024维，COSINE相似度）
        - sparse: 稀疏向量（BM25倒排索引）
        - text: 原文（用于BM25分析，中文分词器）
        - question: 问法
        - answer: 答案正文
        - section_path: 章节路径
        - content_type: 内容类型
        - category: 类别

    BM25函数:
        自动从text字段生成sparse向量
        使用中文分词器分析原文

    索引配置:
        - dense: AUTOINDEX + COSINE（语义相似度）
        - sparse: SPARSE_INVERTED_INDEX + BM25（关键词匹配）

    校验逻辑:
        集合存在时检查是否有混合检索所需字段（dense/sparse/text）
        检查向量维度是否匹配（DIM=1024）
        不匹配时抛出异常，提示重新建库

    异常:
        ValueError: 集合字段或维度不匹配

    设计说明:
        使用全局_ENSURED_COLLECTIONS缓存已检查的集合
        避免重复加载，提升性能
    """
    if (
        client is _CLIENT
        and collection in _ENSURED_COLLECTIONS
    ):
        return

    if client.has_collection(collection):
        # 校验现有集合的字段和维度
        description = client.describe_collection(collection)
        fields = {
            field["name"]: field
            for field in description.get("fields", [])
        }
        if not {"dense", "sparse", "text"}.issubset(fields):
            raise ValueError("现有集合缺少混合检索所需字段，请使用新集合并重新向量化")
        dense_dim = int(fields["dense"].get("params", {}).get("dim", 0))
        if dense_dim != DIM:
            raise ValueError("当前维度不匹配")
        client.load_collection(collection)

    else:
        # 创建新集合
        schema = client.create_schema(
            auto_id=False,
        )

        schema.add_field(
            "id",
            DataType.INT64,
            is_primary=True,
        )

        schema.add_field(
            "dense",
            DataType.FLOAT_VECTOR,
            dim=DIM,
        )

        schema.add_field(
            "question",
            DataType.VARCHAR,
            max_length=2048,
        )

        schema.add_field(
            "answer",
            DataType.VARCHAR,
            max_length=8192,
        )

        schema.add_field(
            "section_path",
            DataType.VARCHAR,
            max_length=512,
        )

        schema.add_field(
            "content_type",
            DataType.VARCHAR,
            max_length=32,
        )

        schema.add_field(
            "category",
            DataType.VARCHAR,
            max_length=255,
        )
        schema.add_field(
            "text",
            DataType.VARCHAR,
            max_length=16384,
            enable_analyzer=True,
            analyzer_params={"type": "chinese"}

        )
        schema.add_field(
            "sparse",
            DataType.SPARSE_FLOAT_VECTOR,
        )

        # 添加BM25函数：自动从text生成sparse向量
        schema.add_function(
            Function(
                name="text_bm25",
                input_field_names=["text"],
                output_field_names=["sparse"],
                function_type=FunctionType.BM25,
            )
        )
        index_params = client.prepare_index_params()

        index_params.add_index(
            field_name="dense",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_params.add_index(
            field_name="sparse",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        client.create_collection(
            collection_name=collection,
            schema=schema,
            index_params=index_params,
        )


        client.load_collection(collection)

    if client is _CLIENT:
        _ENSURED_COLLECTIONS.add(collection)


def upsert_vectors(
    client: MilvusClient,
    rows: list[dict],
    collection: str = COLLECTION,
) -> None:
    """
    按ID新增或覆盖向量记录

    参数:
        client: Milvus客户端
        rows: 记录列表，每条包含id、dense、text等字段
        collection: 集合名称

    处理逻辑:
        按ID插入或更新记录
        sparse向量由BM25函数自动生成，无需传入

    设计说明:
        rows为空时直接返回，避免无效调用
        upsert确保幂等，重复插入同ID记录会覆盖
    """
    if not rows:
        return

    client.upsert(
        collection_name=collection,
        data=rows,
    )


def flush(
    client: MilvusClient,
    collection: str = COLLECTION,
) -> None:
    """
    刷新集合，使新数据可检索

    参数:
        client: Milvus客户端
        collection: 集合名称

    设计说明:
        Milvus异步写入，flush确保数据落盘
        建库完成后调用，确保数据立即可查
    """
    client.flush(
        collection_name=collection,
    )


def _convert_hit(hit: dict) -> dict:
    """
    转换Milvus命中结果为业务字典

    参数:
        hit: Milvus原始命中结果

    返回:
        业务字典，包含id、score、question、answer等字段

    字段映射:
        - id: 知识块ID
        - distance -> score: 相似度分数
        - entity: 包含question、answer等字段

    设计说明:
        统一结果格式，屏蔽Milvus底层结构
    """
    entity = hit["entity"]

    return {
        "id": hit["id"],
        "score": float(hit["distance"]),
        "question": entity["question"],
        "answer": entity["answer"],
        "section_path": entity["section_path"],
        "content_type": entity["content_type"],
        "category": entity["category"],
    }

def category_filter(category: str | None) -> str:
    """
    生成类别过滤表达式

    参数:
        category: 类别名称（可选）

    返回:
        Milvus过滤表达式

    设计说明:
        category为None时返回空字符串（不过滤）
        否则生成 "category == 'xxx'" 表达式
        使用json.dumps确保字符串正确转义
    """
    if category is None:
        return ""
    return "category == " + json.dumps(
        category,
        ensure_ascii=False,
    )

def dense_search(
    client: MilvusClient,
    vector: list[float],
    top_k: int,
    collection: str = COLLECTION,
    category: str | None = None,
) -> list[dict]:
    """
    使用Dense向量执行语义相似度检索

    参数:
        client: Milvus客户端
        vector: 查询向量（1024维）
        top_k: 返回前k条
        collection: 集合名称
        category: 类别过滤（可选）

    返回:
        命中结果列表，按相似度降序

    检索策略:
        COSINE相似度：语义理解，关注"问的是同一件事"

    设计说明:
        纯向量检索，适合语义相近但词面不同的问题
        如："运费谁出" vs "邮费怎么算"
    """
    result = client.search(
        collection_name=collection,
        data=[vector],
        anns_field="dense",
        limit=top_k,
        output_fields=_OUTPUT_FIELDS,
        search_params={
            "metric_type": "COSINE",
        },
        filter=category_filter(category),
    )

    return [
        _convert_hit(hit)
        for hit in result[0]
    ]

def bm25_search(
        client: MilvusClient,
        text: str,
        top_k: int,
        collection: str = COLLECTION,
        category: str | None = None,
) -> list[dict]:
    """
    使用BM25执行关键词匹配检索

    参数:
        client: Milvus客户端
        text: 查询文本
        top_k: 返回前k条
        collection: 集合名称
        category: 类别过滤（可选）

    返回:
        命中结果列表，按BM25分数降序

    检索策略:
        BM25：词面匹配，关注"出现了哪些词"

    设计说明:
        纯关键词检索，适合专有名词、型号等精确匹配
        如："MH-A100" 必须词面命中
    """
    result = client.search(
        collection_name=collection,
        data=[text],
        anns_field="sparse",
        limit=top_k,
        output_fields=_OUTPUT_FIELDS,
        search_params={
            "metric_type": "BM25",
        },
        filter=category_filter(category),
    )
    return [
        _convert_hit(hit)
        for hit in result[0]
    ]

def hybrid_search(
        client: MilvusClient,
        vector: list[float],
        text: str,
        top_k: int,
        collection: str = COLLECTION,
        recall: int = 50,
        category: str | None = None,

) -> list[dict]:
    """
    混合检索：Dense向量 + BM25，RRF融合排序

    参数:
        client: Milvus客户端
        vector: 查询向量（1024维）
        text: 查询文本
        top_k: 返回前k条
        collection: 集合名称
        recall: 每路召回数量（默认50）
        category: 类别过滤（可选）

    返回:
        命中结果列表，按融合分数降序

    检索策略:
        1. Dense向量召回recall条（语义相似）
        2. BM25召回recall条（关键词匹配）
        3. RRF融合两路结果（k=60）
        4. 返回融合后的top_k条

    RRF融合:
        Reciprocal Rank Fusion，倒数排名融合
        两路都排名靠前的结果融合分数更高
        k=60是调参得出的平衡值

    设计说明:
        兼顾语义理解和关键词匹配
        适合大多数用户问题
    """
    expr = category_filter(category)
    dense_request = AnnSearchRequest(
        data=[vector],
        anns_field="dense",
        limit=recall,
        param={
            "metric_type": "COSINE",
        },
        expr=expr,
    )
    sparse_request = AnnSearchRequest(
        data=[text],
        anns_field="sparse",
        limit=recall,
        param={
            "metric_type": "BM25",
        },
        expr=expr,
    )
    result = client.hybrid_search(
        collection_name=collection,
        reqs=[dense_request, sparse_request],
        ranker=RRFRanker(k=60),
        limit=top_k,
        output_fields=_OUTPUT_FIELDS,

    )
    return [
        _convert_hit(hit)
        for hit in result[0]
    ]

def count(
    client: MilvusClient,
    collection: str = COLLECTION,
) -> int:
    """
    返回集合中的记录数量

    参数:
        client: Milvus客户端
        collection: 集合名称

    返回:
        记录总数

    设计说明:
        使用filter="id >= 0"确保统计所有记录
        返回count(*)聚合结果
    """
    result = client.query(
        collection_name=collection,
        filter="id >= 0",
        output_fields=["count(*)"],
    )

    return result[0]["count(*)"]


def drop(
    client: MilvusClient,
    collection: str,
) -> None:
    """
    删除指定集合

    参数:
        client: Milvus客户端
        collection: 集合名称

    警告:
        不可恢复操作，仅用于测试清理

    设计说明:
        检查集合存在性，避免删除不存在的集合报错
    """
    if client.has_collection(collection):
        client.drop_collection(collection)