"""
LLM 客户端模块

本模块提供统一的 LLM 客户端创建接口。
支持 OpenAI 兼容的 API，包括 OpenAI、Azure OpenAI、本地部署的模型等。

配置项从 app.config.settings 读取：
- chat_model: 模型名称
- chat_base_url: API 基础 URL
- chat_api_key: API 密钥
- chat_thinking: 思考模式（部分模型支持，如 DeepSeek）
"""

from langchain_openai import ChatOpenAI

from app.config import settings


def get_chat_model(*, streaming: bool = False) -> ChatOpenAI:
    """
    根据服务器配置创建 LLM 客户端

    不会在创建时发起模型请求，仅配置客户端参数。

    Args:
        streaming: 是否允许调用方使用流式输出（默认 False）

    Returns:
        已配置好模型名、服务地址和密钥的 ChatOpenAI 客户端

    思考模式（Thinking Mode）：
    - 部分模型（如 DeepSeek）支持显式思考步骤
    - 通过 extra_body 参数传递给 API
    - 配置项：settings.chat_thinking（"enabled" 或 "disabled"）

    使用示例：
        model = get_chat_model()
        response = await model.ainvoke([("human", "你好")])
    """
    extra_body = None
    if settings.chat_thinking:
        # 部分模型支持思考模式，通过 extra_body 传递
        extra_body = {"thinking": {"type": settings.chat_thinking}}

    return ChatOpenAI(
        model=settings.chat_model,
        base_url=settings.chat_base_url,
        api_key=settings.chat_api_key,
        streaming=streaming,
        extra_body=extra_body,
    )
