# 模块：可观测性核心
# 提供span上下文管理、trace导出、模型元数据提取
# 支持Langfuse集成和自定义trace sink
# 核心职责：记录每次请求的完整调用链路和模型使用详情

import time
import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from uuid import uuid4
from app.core.langfuse_client import (
    start_langfuse_span,
    end_langfuse_span,
)

logger = logging.getLogger(__name__)

# 全局配置
_langfuse_client = None
_default_trace_sink = None

# 当前活跃的span（使用ContextVar确保协程隔离）
_active_span: ContextVar[dict | None] = ContextVar(
    "active_span",
    default=None,
)

def configure_langfuse(client) -> None:
    """配置Langfuse客户端"""
    global _langfuse_client
    _langfuse_client = client


def configure_trace_sink(sink) -> None:
    """
    配置trace导出函数

    参数:
        sink: 异步函数，接收span记录字典

    设计说明:
        自定义sink用于将trace导出到本地数据库或其他平台
        与Langfuse并行工作，互不干扰
    """
    global _default_trace_sink
    _default_trace_sink = sink


def extract_token_usage(message) -> dict | None:
    """
    从模型响应中提取token使用量

    参数:
        message: 模型响应对象

    返回:
        包含input_tokens/output_tokens/total_tokens的字典，提取失败返回None

    设计说明:
        LangChain的响应对象在usage_metadata中记录token数
        提取失败时返回None而非抛异常，确保可观测性问题不影响业务
    """
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None
    keys = {
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }
    result = {}
    for key in keys:
        value = usage.get(key)
        if type(value) is not int or value < 0:
            return None
        result[key] = value

    return result


def extract_model_name(message) -> str | None:
    """
    从模型响应中提取模型名称

    参数:
        message: 模型响应对象

    返回:
        模型名称字符串，提取失败返回None

    设计说明:
        优先查找response_metadata.model_name，回退到.model
        不同提供商的响应格式略有差异，此函数兼容多种格式
    """
    metadata = getattr(message, "response_metadata", None)

    if not isinstance(metadata, dict):
        return None

    for key in ("model_name", "model"):
        value = metadata.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


@asynccontextmanager
async def span(
    name: str,
    sink=None,
    *,
    timeout: float = 0.05,
    generation: bool = False,
):
    """
    可观测性span上下文管理器

    参数:
        name: span名称（如"answer_model"、"retrieval"）
        sink: 自定义trace导出函数（可选）
        timeout: 导出超时（秒，默认0.05）
        generation: 是否为模型生成节点

    用法:
        async with span("answer_model", generation=True) as record:
            response = await model.ainvoke(messages)
            record["token_usage"] = extract_token_usage(response)
            record["model"] = extract_model_name(response)

    记录字段:
        - trace_id: 追踪ID（同一请求的所有span共享）
        - span_id: span ID（当前节点唯一标识）
        - parent_id: 父span ID
        - name: span名称
        - status: 状态（ok/error/cancelled）
        - duration_ms: 耗时（毫秒）
        - error_type: 错误类型（失败时）
        - token_usage: token使用量（generation节点）
        - model: 模型名称（generation节点）

    trace导出:
        1. 同步到Langfuse（如果已配置）
        2. 导出到自定义sink（如果已配置）
        3. 超时或失败不抛异常，确保不影响业务

    设计说明:
        使用ContextVar实现协程隔离，每个请求有独立的span栈
        父子span自动关联，形成完整调用树
        generation=True时自动提取模型和token信息
    """
    parent = _active_span.get()
    effective_sink = sink
    if effective_sink is None and parent is not None:
        effective_sink = parent.get("_sink")
    if effective_sink is None:
        effective_sink = _default_trace_sink

    # 初始化span记录
    record = {
        "trace_id": parent["trace_id"] if parent is not None else uuid4().hex,
        "span_id": uuid4().hex,
        "parent_id": parent["span_id"] if parent is not None else None,
        "name": name,
        "status": "ok",
        "_generation": generation,
        "_sink": effective_sink,
    }

    # 启动Langfuse observation
    observation = start_langfuse_span(
        _langfuse_client,
        name=name,
        generation=generation,
        trace_id=record["trace_id"],
        parent_span_id=(
            parent.get("_langfuse_span_id")
            if parent is not None
            else None
        ),
    )

    record["_langfuse_span_id"] = (
        observation.id if observation is not None else None
    )

    # 设置为当前活跃span
    token = _active_span.set(record)
    started = time.monotonic()
    try:
        yield record
    except BaseException as error:
        record["status"] = (
            "cancelled"
            if isinstance(error, asyncio.CancelledError)
            else "error"
        )
        record["error_type"] = type(error).__name__

        raise
    finally:
        record["duration_ms"] = round(
            (time.monotonic() - started) * 1000,
            3,
        )
        _active_span.reset(token)

        # 结束Langfuse observation
        end_langfuse_span(observation, record)

        # 导出到自定义sink
        if effective_sink is not None:
            allowed_fields = (
                "trace_id",
                "span_id",
                "parent_id",
                "name",
                "status",
                "duration_ms",
                "error_type",
            )
            payload = {
                key: record[key]
                for key in allowed_fields
                if key in record
            }
            payload["kind"] = (
                "generation" if record["_generation"] else "span"
            )

            if "intent" in record:
                payload["intent"] = record["intent"]

            # generation节点额外导出模型和token信息
            if record["_generation"]:
                if "model" in record:
                    payload["model"] = record["model"]

                usage = record.get("token_usage")
                if isinstance(usage, dict):
                    for key in (
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                    ):
                        if key in usage:
                            payload[key] = usage[key]

            try:
                await asyncio.wait_for(
                    effective_sink(payload),
                    timeout=timeout,
                )
            except Exception:
                logger.warning(
                    "trace export failed; span_id=%s",
                    record["span_id"],
                )
