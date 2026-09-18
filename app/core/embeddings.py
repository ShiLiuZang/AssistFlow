"""Ch03：调用嵌入模型，把文本转换成向量。"""

# 后续教学逐步实现 embed_texts 和 embed_query。
from openai import AsyncOpenAI

from app.config import settings

_CLIENT: AsyncOpenAI | None = None


def _client() -> AsyncOpenAI:
    global _CLIENT

    if _CLIENT is None:
        _CLIENT = AsyncOpenAI(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
        )

    return _CLIENT
async def embed_texts(
    texts: list[str],
) -> list[list[float]]:
    vectors: list[list[float]] = []

    for start in range(0, len(texts), 10):
        batch = texts[start:start + 10]

        response = await _client().embeddings.create(
            model=settings.embed_model,
            input=batch,
        )

        vectors.extend(
            item.embedding
            for item in response.data
        )

    return vectors
async def embed_query(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]