import asyncio
import functools

from concurrent.futures import ThreadPoolExecutor

from pymilvus import (
    DataType,
    Function,
    FunctionType,
    MilvusClient,
)

from app.config import settings


COLLECTION = settings.milvus_collection
DIM = 1024

_OUTPUT_FIELDS = [
    "question",
    "answer",
    "section_path",
    "content_type",
    "category",
]

_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="milvus",
)

_CLIENT: MilvusClient | None = None
_ENSURED_COLLECTIONS: set[str] = set()


async def acall(function, *args, **kwargs):
    """在线程池中运行同步的 pymilvus 操作。"""
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
    """返回 Milvus 客户端；测试可传入独立 URI。"""
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
    """如果集合不存在就创建，存在则加载。"""
    if (
        client is _CLIENT
        and collection in _ENSURED_COLLECTIONS
    ):
        return

    if client.has_collection(collection):
        description=client.describe_collection(collection)
        fileds={
             filed["name"]:filed
             for filed in description.get("fields", [])
         }
        if not {"dense","sparse","text"}.issubset(fileds):
           raise ValueError("现有集合缺少 Ch04 字段，请使用新集合并重新向量化")
        dense_dim=int (fileds["dense"].get("params",{}).get("dim",0))
        if dense_dim!=DIM:
           raise ValueError("当前维度不匹配")
        client.load_collection(collection)

    else:
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
            analyzer_params={"type":"chinese"}

        )
        schema.add_field(
            "sparse",
            DataType.SPARSE_FLOAT_VECTOR,
        )

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
    """按 ID 新增或覆盖向量记录。"""
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
    """要求 Milvus 刷新集合，使新数据可以被检索。"""
    client.flush(
        collection_name=collection,
    )


def _convert_hit(hit: dict) -> dict:
    """把 Milvus 命中结果转换为业务字典。"""
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


def dense_search(
    client: MilvusClient,
    vector: list[float],
    top_k: int,
    collection: str = COLLECTION,
) -> list[dict]:
    """使用 Dense 向量执行语义相似度检索。"""
    result = client.search(
        collection_name=collection,
        data=[vector],
        anns_field="dense",
        limit=top_k,
        output_fields=_OUTPUT_FIELDS,
        search_params={
            "metric_type": "COSINE",
        },
    )

    return [
        _convert_hit(hit)
        for hit in result[0]
    ]


def count(
    client: MilvusClient,
    collection: str = COLLECTION,
) -> int:
    """返回集合中的记录数量。"""
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
    """删除指定集合，只用于明确的测试清理。"""
    if client.has_collection(collection):
        client.drop_collection(collection)