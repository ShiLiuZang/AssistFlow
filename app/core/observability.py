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
_active_span: ContextVar[dict | None] = ContextVar(
    "active_span",
    default=None,
)
def configure_langfuse(client) -> None:
    global _langfuse_client
    _langfuse_client = client

@asynccontextmanager
async def span(name: str, sink=None, *, timeout: float = 0.05):
    parent = _active_span.get()

    record = {
        "trace_id": parent["trace_id"] if parent is not None else uuid4().hex,
        "span_id": uuid4().hex,
        "parent_id": parent["span_id"] if parent is not None else None,
        "name": name,
        "status": "ok",
    }
    observation = start_langfuse_span(
        _langfuse_client,
        name=name,
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
        if sink is not None:
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

            try:
                await asyncio.wait_for(
                    sink(payload),
                    timeout=timeout,
                )
            except Exception:
                logger.warning(
                    "trace export failed; span_id=%s",
                    record["span_id"],
                )