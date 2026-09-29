# 模块：Langfuse客户端封装
# 封装Langfuse可观测性平台的客户端初始化、span生命周期管理
# 支持优雅关闭、超时控制、错误容错
# 核心职责：将可观测性数据同步到Langfuse，不阻塞业务流程

import asyncio
import logging

from app.config import Settings


logger = logging.getLogger(__name__)


def create_langfuse_client(config: Settings):
    """
    创建Langfuse客户端

    参数:
        config: 应用配置对象

    返回:
        Langfuse客户端实例，配置未启用或初始化失败时返回None

    设计说明:
        配置未启用时静默返回None，不视为错误
        初始化失败时记录警告但不抛异常，确保服务可启动
        2秒超时确保初始化不阻塞启动流程
    """
    if not config.langfuse_configured:
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=config.langfuse_public_key.strip(),
            secret_key=config.langfuse_secret_key.strip(),
            base_url=config.langfuse_base_url.strip(),
            timeout=2,
        )
    except Exception as error:
        logger.warning(
            "Langfuse initialization failed; error_type=%s",
            type(error).__name__,
        )
        return None


async def close_langfuse_client(client) -> None:
    """
    关闭Langfuse客户端

    参数:
        client: Langfuse客户端实例

    设计说明:
        客户端为None时直接返回，兼容未启用场景
        调用shutdown等待缓冲区数据上传完成
        3秒超时确保关闭流程不无限等待
        失败时记录警告但不抛异常，避免影响服务关闭
    """
    if client is None:
        return
    try:
        await asyncio.wait_for(
            asyncio.to_thread(client.shutdown),
            timeout=3,
        )
    except TimeoutError:
        logger.warning("Langfuse shutdown timed out")
    except Exception as error:
        logger.warning(
            "Langfuse shutdown failed; error_type=%s",
            type(error).__name__,
        )


def start_langfuse_span(
    client,
    *,
    name: str,
    trace_id: str,
    parent_span_id: str | None = None,
    generation: bool = False,
):
    """
    启动Langfuse观测span

    参数:
        client: Langfuse客户端实例
        name: span名称
        trace_id: 追踪ID
        parent_span_id: 父span ID（可选）
        generation: 是否为模型生成节点

    返回:
        observation对象，客户端为None或启动失败时返回None

    观测类型:
        generation=True: 标记为模型生成节点，记录token和成本
        generation=False: 标记为普通span，记录耗时和状态

    设计说明:
        启动失败时记录警告并返回None，不抛异常
        确保可观测性问题不影响业务流程
    """
    if client is None:
        return None

    trace_context = {"trace_id": trace_id}
    if parent_span_id is not None:
        trace_context["parent_span_id"] = parent_span_id

    try:
        return client.start_observation(
            name=name,
            as_type="generation" if generation else "span",
            trace_context=trace_context,
        )
    except Exception as error:
        logger.warning(
            "Langfuse span start failed; error_type=%s",
            type(error).__name__,
        )
        return None


def end_langfuse_span(observation, record: dict) -> None:
    """
    结束Langfuse观测span

    参数:
        observation: observation对象
        record: span记录字典

    记录字段:
        - status: 状态（ok/error/cancelled）
        - duration_ms: 耗时（毫秒）
        - intent: 意图分类（可选）
        - intent_confidence: 意图置信度（可选）
        - token_usage: token使用量（可选）
        - model: 模型名称（generation节点）
        - error_type: 错误类型（失败时）

    状态映射:
        ok → DEFAULT
        error → ERROR
        cancelled → WARNING

    设计说明:
        observation为None时直接返回，兼容启动失败场景
        使用try-finally确保observation.end()一定被调用
        失败时记录警告但不抛异常，避免污染业务异常
    """
    if observation is None:
        return

    level = {
        "ok": "DEFAULT",
        "error": "ERROR",
        "cancelled": "WARNING",
    }.get(record["status"], "ERROR")
    metadata = {
        "local_span_id": record["span_id"],
        "status": record["status"],
        "duration_ms": record["duration_ms"],
    }

    if "intent" in record:
        metadata["intent"] = record["intent"]
        metadata["intent_confidence"] = record["intent_confidence"]
    if "token_usage" in record:
        metadata["token_usage"] = record["token_usage"]
    extra = {}

    # generation节点额外记录模型和token使用量
    if record.get("_generation"):
        model_name = record.get("model")

        if model_name is not None:
            extra["model"] = model_name

        usage = record.get("token_usage")

        if usage is not None:
            extra["usage_details"] = {
                "input": usage["input_tokens"],
                "output": usage["output_tokens"],
                "total": usage["total_tokens"],
            }
    try:
        try:
            observation.update(
                level=level,
                status_message=record.get("error_type"),
                metadata=metadata,
                **extra,
            )

        finally:
            observation.end()
    except Exception as error:
        logger.warning(
            "Langfuse span finish failed; error_type=%s",
            type(error).__name__,
        )
