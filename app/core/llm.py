from langchain_openai import ChatOpenAI

from app.config import settings


def get_chat_model(*, streaming: bool = False) -> ChatOpenAI:
    """根据服务器配置创建模型客户端，不会在创建时发起模型请求。

    Args:
        streaming: 是否允许调用方使用流式输出。

    Returns:
        已配置好模型名、服务地址和密钥的 ChatOpenAI 客户端。
    """
    extra_body = None
    if settings.chat_thinking:
        # 当前供应商的思考模式与强制工具调用不兼容，结构化提取需要关闭它。
        extra_body = {"thinking": {"type": settings.chat_thinking}}

    return ChatOpenAI(
        model=settings.chat_model,
        base_url=settings.chat_base_url,
        api_key=settings.chat_api_key,
        streaming=streaming,
        extra_body=extra_body,
    )
