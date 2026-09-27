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
_langfuse_client = None
_default_trace_sink = None
_active_span: ContextVar[dict | None] = ContextVar(
    "active_span",
    default=None,
)
def configure_langfuse(client) -> None:
    global _langfuse_client
    _langfuse_client = client


def configure_trace_sink(sink) -> None:
    global _default_trace_sink
    _default_trace_sink = sink


def extract_token_usage(message) -> dict | None:
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
    parent = _active_span.get()
    effective_sink = sink
    if effective_sink is None and parent is not None:
        effective_sink = parent.get("_sink")
    if effective_sink is None:
        effective_sink = _default_trace_sink

    record = {
        "trace_id": parent["trace_id"] if parent is not None else uuid4().hex,
        "span_id": uuid4().hex,
        "parent_id": parent["span_id"] if parent is not None else None,
        "name": name,
        "status": "ok",
        "_generation": generation,
        "_sink": effective_sink,
    }
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
        end_langfuse_span(observation, record)
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
