from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import math
@dataclass(frozen=True)
class Price:
    input_per_million: Decimal
    output_per_million: Decimal
    currency: str
    as_of: str
def build_intent_index(observations:list[dict])->dict[str,str]:
    candidates:dict[str,set[str]] = {}
    for observation in observations:
        if observation.get("name") !="classify":
            continue

        trace_id=observation.get("traceId")
        metadata=observation.get("metadata")
        if not isinstance(trace_id, str) or not trace_id.strip():
            continue
        if not isinstance(metadata, dict):
            continue

        intent=metadata.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            continue
        candidates.setdefault(trace_id, set()).add(intent.strip())
    result = {}

    for trace_id, intents in candidates.items():
        if len(intents) == 1:
            intent = next(iter(intents))
            result[trace_id] = intent

    return result
def reported_total_tokens(observation: dict) -> int | None:
    metadata = observation.get("metadata")

    if not isinstance(metadata, dict):
        return None

    usage = metadata.get("token_usage")

    if not isinstance(usage, dict):
        return None

    total = usage.get("total_tokens")

    if type(total) is not int or total < 0:
        return None

    return total
def unique_observations(observations: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}

    for observation in observations:
        observation_id = observation.get("id")

        if (
            not isinstance(observation_id, str)
            or not observation_id.strip()
        ):
            raise ValueError("观测记录缺少有效的 id")

        if observation_id in by_id:
            if by_id[observation_id] != observation:
                raise ValueError("同一观测 id 对应不同内容")

            continue

        by_id[observation_id] = observation

    return list(by_id.values())
def aggregate_usage(observations: list[dict]) -> list[dict]:
    observations = unique_observations(observations)
    intent_index = build_intent_index(observations)
    groups: dict[str, dict] = {}

    for observation in observations:
        if observation.get("type") != "GENERATION":
            continue

        trace_id = observation.get("traceId")
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError("模型观测缺少有效的 traceId")

        if observation.get("name") == "summary_model":
            intent = "后台摘要"
        else:
            intent = intent_index.get(trace_id, "未归类")

        group = groups.setdefault(
            intent,
            {
                "traces": set(),
                "generation_count": 0,
                "measured_count": 0,
                "missing_usage_count": 0,
                "known_tokens": 0,
            },
        )

        group["traces"].add(trace_id)
        group["generation_count"] += 1

        total = reported_total_tokens(observation)

        if total is None:
            group["missing_usage_count"] += 1
        else:
            group["measured_count"] += 1
            group["known_tokens"] += total

    rows = []

    for intent, group in groups.items():
        rows.append({
            "intent": intent,
            "count": len(group["traces"]),
            "generation_count": group["generation_count"],
            "measured_count": group["measured_count"],
            "missing_usage_count": group["missing_usage_count"],
            "known_tokens": group["known_tokens"],
        })

    return sorted(
        rows,
        key=lambda row: (-row["known_tokens"], row["intent"]),
    )
def build_cost_report(observations: list[dict]) -> dict:
    observations = unique_observations(observations)
    groups = aggregate_usage(observations)

    total_known_tokens = sum(
        group["known_tokens"]
        for group in groups
    )
    missing_usage_count = sum(
        group["missing_usage_count"]
        for group in groups
    )

    trace_ids = {
        observation["traceId"]
        for observation in observations
        if observation.get("type") == "GENERATION"
    }

    rows = []

    for group in groups:
        complete = group["missing_usage_count"] == 0

        rows.append({
            **group,
            "tokens": (
                group["known_tokens"]
                if complete
                else None
            ),
            "avg_tokens": (
                round(group["known_tokens"] / group["count"], 2)
                if complete
                else None
            ),
            "share": (
                round(
                    group["known_tokens"] / total_known_tokens,
                    4,
                )
                if missing_usage_count == 0
                and total_known_tokens > 0
                else None
            ),
        })

    return {
        "rows": rows,
        "known_tokens": total_known_tokens,
        "total_tokens": (
            total_known_tokens
            if missing_usage_count == 0
            else None
        ),
        "total_requests": len(trace_ids),
        "generation_count": sum(
            group["generation_count"]
            for group in groups
        ),
        "missing_usage_count": missing_usage_count,
        "usage_complete": missing_usage_count == 0,
    }
def to_generation_rows(observations: list[dict]) -> list[dict]:
    observations = unique_observations(observations)
    intent_index = build_intent_index(observations)
    rows = []

    for observation in observations:
        if observation.get("type") != "GENERATION":
            continue

        trace_id = observation.get("traceId")
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError("模型观测缺少有效的 traceId")

        metadata = observation.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        usage = metadata.get("token_usage")
        if not isinstance(usage, dict):
            usage = {}

        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")

        if any(
            type(value) is not int or value < 0
            for value in (input_tokens, output_tokens)
        ):
            input_tokens = None
            output_tokens = None

        model = observation.get("model")
        if isinstance(model, str) and model.strip():
            model = model.strip()
        else:
            model = None

        if observation.get("name") == "summary_model":
            intent = "后台摘要"
        else:
            intent = intent_index.get(trace_id, "unknown")

        rows.append({
            "trace_id": trace_id,
            "generation_id": observation["id"],
            "intent": intent,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": metadata.get("duration_ms"),
        })

    return rows
def estimate_generation_cost(
    row: dict,
    prices: dict[str, Price],
) -> dict | None:
    input_tokens = row.get("input_tokens")
    output_tokens = row.get("output_tokens")

    if any(
        type(value) is not int or value < 0
        for value in (input_tokens, output_tokens)
    ):
        return None

    model = row.get("model")
    if not isinstance(model, str) or not model.strip():
        return None

    price = prices.get(model)
    if price is None:
        return None

    for rate in (
        price.input_per_million,
        price.output_per_million,
    ):
        if (
            not isinstance(rate, Decimal)
            or not rate.is_finite()
            or rate < 0
        ):
            raise ValueError("模型价格必须是有限的非负 Decimal")

    if not price.currency.strip() or not price.as_of.strip():
        raise ValueError("模型价格必须包含币种和价格版本")

    amount = (
        input_tokens * price.input_per_million
        + output_tokens * price.output_per_million
    ) / Decimal("1000000")

    return {
        "amount": amount,
        "currency": price.currency,
        "price_version": price.as_of,
    }
def cost_by_intent(
    rows: list[dict],
    prices: dict[str, Price] | None = None,
) -> dict:
    prices = prices if prices is not None else {}
    groups = {}
    seen = {}

    for row in rows:
        trace_id = row.get("trace_id")
        generation_id = row.get("generation_id")

        if any(
            not isinstance(value, str) or not value.strip()
            for value in (trace_id, generation_id)
        ):
            raise ValueError("模型调用缺少有效的 trace_id 或 generation_id")

        key = (trace_id, generation_id)

        if key in seen:
            if seen[key] != row:
                raise ValueError("同一模型调用对应不同内容")
            continue

        seen[key] = row

        intent = row.get("intent") or "unknown"
        group = groups.setdefault(
            intent,
            {
                "traces": set(),
                "generations": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "unknown_usage": 0,
                "unpriced": 0,
                "priced_subtotals": {},
                "price_versions": set(),
                "durations": [],
            },
        )

        group["traces"].add(trace_id)
        group["generations"] += 1
        duration = row.get("duration_ms")

        if (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and math.isfinite(duration)
            and duration >= 0
        ):
            group["durations"].append(duration)
        input_tokens = row.get("input_tokens")
        output_tokens = row.get("output_tokens")

        if any(
            type(value) is not int or value < 0
            for value in (input_tokens, output_tokens)
        ):
            group["unknown_usage"] += 1
        else:
            group["input_tokens"] += input_tokens
            group["output_tokens"] += output_tokens

        estimate = estimate_generation_cost(row, prices)

        if estimate is None:
            group["unpriced"] += 1
            continue

        currency = estimate["currency"]
        subtotals = group["priced_subtotals"]

        subtotals[currency] = (
            subtotals.get(currency, Decimal("0"))
            + estimate["amount"]
        )
        group["price_versions"].add(estimate["price_version"])

    for group in groups.values():
        group["requests"] = len(group.pop("traces"))
        durations = sorted(group.pop("durations"))

        group["duration_samples"] = len(durations)
        group["p95_generation_ms"] = (
            durations[math.ceil(len(durations) * 0.95) - 1]
            if durations
            else None
        )
        group["price_versions"] = sorted(group["price_versions"])
        group["priced_subtotals"] = {
            currency: str(amount)
            for currency, amount in group["priced_subtotals"].items()
        }
        group["estimate_complete"] = group["unpriced"] == 0

    return groups


def make_cost_report(
    generation_rows: list[dict],
    prices: dict[str, Price] | None = None,
    *,
    source: str,
) -> dict:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("报表必须说明数据来源")

    groups = cost_by_intent(generation_rows, prices)

    rows = [
        {"intent": intent, **group}
        for intent, group in groups.items()
    ]
    rows.sort(
        key=lambda row: (
            -(row["input_tokens"] + row["output_tokens"]),
            row["intent"],
        )
    )

    trace_ids = {row["trace_id"] for row in generation_rows}
    unknown_usage = sum(row["unknown_usage"] for row in rows)
    unpriced = sum(row["unpriced"] for row in rows)

    return {
        "schema_version": 1,
        "meta": {
            "source": source.strip(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "provided_generations",
            "pricing_basis": "input_output_only",
        },
        "rows": rows,
        "summary": {
            "requests": len(trace_ids),
            "generations": sum(row["generations"] for row in rows),
            "known_input_tokens": sum(row["input_tokens"] for row in rows),
            "known_output_tokens": sum(row["output_tokens"] for row in rows),
            "unknown_usage": unknown_usage,
            "unpriced": unpriced,
            "usage_complete": unknown_usage == 0,
            "estimate_complete": unpriced == 0,
        },
    }
