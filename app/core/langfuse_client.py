import asyncio
import logging

from app.config import Settings


logger = logging.getLogger(__name__)


def create_langfuse_client(config: Settings):
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
