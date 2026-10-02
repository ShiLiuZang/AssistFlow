"""
向量化模块
负责将文本转换为向量表示，用于语义相似度检索
封装 OpenAI 兼容的 Embedding API，支持批量处理和单条查询
是 RAG 系统中连接自然语言和向量检索的桥梁
"""

from openai import AsyncOpenAI

from app.config import settings

# 全局客户端实例，延迟初始化以节省资源
_CLIENT: AsyncOpenAI | None = None


def _client() -> AsyncOpenAI:
    """
    获取或创建 OpenAI 客户端实例

    返回:
        配置好的 AsyncOpenAI 客户端

    设计原因:
        延迟初始化，只在首次调用时创建客户端
        避免导入模块时就建立连接，提高启动速度
    """
    global _CLIENT

    if _CLIENT is None:
        _CLIENT = AsyncOpenAI(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
            timeout=settings.chat_timeout_seconds,
            max_retries=settings.chat_max_retries,
        )

    return _CLIENT

async def embed_texts(
    texts: list[str],
) -> list[list[float]]:
    """
    批量向量化文本列表

    参数:
        texts: 待向量化的文本列表

    返回:
        向量列表，每个向量是一个浮点数列表，与输入文本一一对应

    批处理策略:
        每批最多处理10条文本，避免单次请求过大导致超时或失败
        多批次顺序执行，确保结果顺序与输入一致

    安全保障:
        验证返回结果的索引顺序，防止 API 返回乱序或缺失数据
        如果索引不连续或重复，抛出异常避免数据错误
    """
    vectors: list[list[float]] = []

    # 按每批10条文本分批处理
    for start in range(0, len(texts), 10):
        batch = texts[start:start + 10]

        # 调用 Embedding API
        response = await _client().embeddings.create(
            model=settings.embed_model,
            input=batch,
        )
        # 按索引排序，确保结果顺序正确
        items = sorted(response.data, key=lambda item: item.index)
        indices = [item.index for item in items]
        excepted_indices = list(range(len(batch)))
        # 验证索引连续性，防止返回结果错位或缺失
        if indices != excepted_indices:
            raise ValueError("嵌入结果失败,重复或者越界")
        # 提取向量并追加到结果列表
        vectors.extend(
            item.embedding
            for item in items
        )

    return vectors

async def embed_query(text: str) -> list[float]:
    """
    向量化单条查询文本

    参数:
        text: 查询文本

    返回:
        单个向量（浮点数列表）

    设计原因:
        为单条查询提供便捷接口，内部调用批量接口
        避免重复编写单条处理逻辑
    """
    vectors = await embed_texts([text])
    return vectors[0]
