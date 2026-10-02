"""可观测性：span 上下文、token 提取、Langfuse 适配、按意图的成本报表。"""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.config import Settings
from app.core import cost_report, langfuse_client, observability
from app.core.cost_report import Price
from app.core.observability import extract_model_name, extract_token_usage, span
from app.schemas.cost_report import CostReport


class TestExtractors:
    def test_token_usage(self):
        message = AIMessage(content="", usage_metadata={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})
        assert extract_token_usage(message) == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}

    @pytest.mark.parametrize(
        "usage",
        [None, "x", {"input_tokens": 1, "output_tokens": 2}, {"input_tokens": -1, "output_tokens": 2, "total_tokens": 1},
         {"input_tokens": 1.0, "output_tokens": 2, "total_tokens": 3}],
    )
    def test_token_usage_invalid(self, usage):
        assert extract_token_usage(SimpleNamespace(usage_metadata=usage)) is None

    @pytest.mark.parametrize(
        "metadata,expected",
        [({"model_name": " gpt "}, "gpt"), ({"model": "m2"}, "m2"), ({"model_name": " ", "model": "m3"}, "m3"),
         ({}, None), (None, None)],
    )
    def test_model_name(self, metadata, expected):
        assert extract_model_name(SimpleNamespace(response_metadata=metadata)) == expected


class TestSpan:
    async def test_nested_spans_share_trace_and_export(self):
        exported = []

        async def sink(payload):
            exported.append(payload)

        async with span("outer", sink) as outer:
            async with span("inner", generation=True) as inner:
                inner["model"] = "m"
                inner["token_usage"] = {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
                inner["secret"] = "不导出"
            outer["intent"] = "物流"

        inner_payload, outer_payload = exported
        assert inner_payload["trace_id"] == outer_payload["trace_id"]
        assert inner_payload["parent_id"] == outer_payload["span_id"]
        assert outer_payload["parent_id"] is None
        assert inner_payload["kind"] == "generation"
        assert inner_payload["model"] == "m"
        assert inner_payload["total_tokens"] == 3
        assert "secret" not in inner_payload
        assert outer_payload["intent"] == "物流"
        assert outer_payload["kind"] == "span"
        assert outer_payload["duration_ms"] >= 0

    async def test_error_status_recorded_and_reraised(self):
        exported = []

        async def sink(payload):
            exported.append(payload)

        with pytest.raises(KeyError):
            async with span("boom", sink):
                raise KeyError("x")

        assert exported[0]["status"] == "error"
        assert exported[0]["error_type"] == "KeyError"

    async def test_cancelled_status(self):
        exported = []

        async def sink(payload):
            exported.append(payload)

        async def work():
            async with span("slow", sink):
                await asyncio.sleep(10)

        task = asyncio.create_task(work())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert exported[0]["status"] == "cancelled"

    async def test_default_sink_used(self):
        exported = []

        async def sink(payload):
            exported.append(payload["name"])

        observability.configure_trace_sink(sink)
        async with span("default"):
            pass
        assert exported == ["default"]

    async def test_sink_failure_and_timeout_swallowed(self):
        async def failing(payload):
            raise RuntimeError("db down")

        async def slow(payload):
            await asyncio.sleep(1)

        async with span("a", failing):
            pass
        async with span("b", slow, timeout=0.01):
            pass

    async def test_langfuse_observation_lifecycle(self):
        class Observation:
            def __init__(self, name):
                self.id = f"lf-{name}"
                self.updates = []
                self.ended = False

            def update(self, **kwargs):
                self.updates.append(kwargs)

            def end(self):
                self.ended = True

        class Client:
            def __init__(self):
                self.started = []

            def start_observation(self, *, name, as_type, trace_context):
                self.started.append((name, as_type, trace_context))
                return Observation(name)

        client = Client()
        observability.configure_langfuse(client)

        async with span("outer") as outer:
            async with span("gen", generation=True) as record:
                record["model"] = "m"
                record["token_usage"] = {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}

        (outer_name, outer_type, outer_ctx), (gen_name, gen_type, gen_ctx) = client.started
        assert (outer_type, gen_type) == ("span", "generation")
        assert gen_ctx == {"trace_id": outer["trace_id"], "parent_span_id": "lf-outer"}


class TestLangfuseClient:
    def test_not_configured_returns_none(self):
        assert langfuse_client.create_langfuse_client(Settings()) is None

    def test_start_without_client(self):
        assert langfuse_client.start_langfuse_span(None, name="x", trace_id="t") is None

    def test_start_failure_returns_none(self):
        class Broken:
            def start_observation(self, **kwargs):
                raise RuntimeError("down")

        assert langfuse_client.start_langfuse_span(Broken(), name="x", trace_id="t") is None

    def test_end_maps_status_and_usage(self):
        calls = []

        class Observation:
            def update(self, **kwargs):
                calls.append(("update", kwargs))

            def end(self):
                calls.append(("end", None))

        langfuse_client.end_langfuse_span(Observation(), {
            "status": "error", "span_id": "s", "duration_ms": 1.0, "error_type": "KeyError",
            "_generation": True, "model": "m", "intent": "物流", "intent_confidence": 0.9,
            "token_usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        })

        (_, update), (kind, _) = calls
        assert kind == "end"
        assert update["level"] == "ERROR"
        assert update["status_message"] == "KeyError"
        assert update["usage_details"] == {"input": 1, "output": 2, "total": 3}
        assert update["metadata"]["intent"] == "物流"

    def test_end_still_closes_when_update_fails(self):
        ended = []

        class Observation:
            def update(self, **kwargs):
                raise RuntimeError("x")

            def end(self):
                ended.append(True)

        langfuse_client.end_langfuse_span(Observation(), {"status": "ok", "span_id": "s", "duration_ms": 1})
        assert ended == [True]

    async def test_close(self):
        closed = []
        await langfuse_client.close_langfuse_client(None)
        await langfuse_client.close_langfuse_client(SimpleNamespace(shutdown=lambda: closed.append(1)))

        def broken():
            raise RuntimeError("x")

        await langfuse_client.close_langfuse_client(SimpleNamespace(shutdown=broken))
        assert closed == [1]


def classify_obs(obs_id, trace, intent):
    return {"id": obs_id, "traceId": trace, "name": "classify", "type": "SPAN", "metadata": {"intent": intent}}


def gen(obs_id, trace, total=None, name="answer_model", **extra):
    metadata = {}
    if total is not None:
        metadata["token_usage"] = {"total_tokens": total, "input_tokens": total - 1, "output_tokens": 1}
    return {"id": obs_id, "traceId": trace, "type": "GENERATION", "name": name, "metadata": metadata, **extra}


class TestCostAggregation:
    def test_intent_index_ignores_conflicts(self):
        index = cost_report.build_intent_index([
            classify_obs("1", "t1", "物流"),
            classify_obs("2", "t2", "订单"),
            classify_obs("3", "t2", "物流"),
            classify_obs("4", "t3", " "),
            {"name": "classify", "traceId": "t4", "metadata": None},
        ])
        assert index == {"t1": "物流"}

    def test_unique_observations(self):
        a = gen("g1", "t1", 10)
        assert cost_report.unique_observations([a, dict(a)]) == [a]
        with pytest.raises(ValueError, match="不同内容"):
            cost_report.unique_observations([a, {**a, "name": "x"}])
        with pytest.raises(ValueError, match="id"):
            cost_report.unique_observations([{"id": ""}])

    def test_build_cost_report(self):
        report = cost_report.build_cost_report([
            classify_obs("c1", "t1", "物流"),
            gen("g1", "t1", 100),
            gen("g2", "t1", 50),
            gen("g3", "t2", 30, name="summary_model"),
            gen("g4", "t3", 20),
        ])

        rows = {row["intent"]: row for row in report["rows"]}
        assert rows["物流"]["tokens"] == 150
        assert rows["物流"]["count"] == 1
        assert rows["后台摘要"]["known_tokens"] == 30
        assert rows["未归类"]["share"] == pytest.approx(0.1)
        assert report["total_tokens"] == 200
        assert report["total_requests"] == 3
        assert report["usage_complete"] is True

    def test_missing_usage_makes_totals_unknown(self):
        report = cost_report.build_cost_report([gen("g1", "t1", 100), gen("g2", "t1")])
        assert report["total_tokens"] is None
        assert report["rows"][0]["tokens"] is None
        assert report["rows"][0]["share"] is None
        assert report["missing_usage_count"] == 1

    def test_generation_without_trace_rejected(self):
        with pytest.raises(ValueError, match="traceId"):
            cost_report.aggregate_usage([gen("g1", "", 1)])


PRICES = {"m": Price(Decimal("2"), Decimal("8"), "CNY", "2026-01")}


def row(gid, trace, intent="物流", model="m", inp=1000, out=500, duration=10):
    return {"trace_id": trace, "generation_id": gid, "intent": intent, "model": model,
            "input_tokens": inp, "output_tokens": out, "duration_ms": duration}


class TestCostByIntent:
    def test_to_generation_rows(self):
        rows = cost_report.to_generation_rows([
            classify_obs("c1", "t1", "物流"),
            gen("g1", "t1", 10, model=" m "),
            gen("g2", "t2", name="summary_model"),
        ])
        assert rows[0] == {"trace_id": "t1", "generation_id": "g1", "intent": "物流", "model": "m",
                           "input_tokens": 9, "output_tokens": 1, "duration_ms": None}
        assert rows[1]["intent"] == "后台摘要"
        assert rows[1]["input_tokens"] is None

    def test_estimate_generation_cost(self):
        assert cost_report.estimate_generation_cost(row("g", "t"), PRICES) == {
            "amount": Decimal("0.006"), "currency": "CNY", "price_version": "2026-01",
        }

    @pytest.mark.parametrize("override", [{"model": "unknown"}, {"model": None}, {"input_tokens": None}])
    def test_unpriced(self, override):
        assert cost_report.estimate_generation_cost({**row("g", "t"), **override}, PRICES) is None

    def test_invalid_price_rejected(self):
        with pytest.raises(ValueError):
            cost_report.estimate_generation_cost(row("g", "t"), {"m": Price(Decimal("-1"), Decimal("1"), "CNY", "v")})
        with pytest.raises(ValueError):
            cost_report.estimate_generation_cost(row("g", "t"), {"m": Price(Decimal("1"), Decimal("1"), " ", "v")})

    def test_groups_and_p95(self):
        rows = [row(f"g{i}", f"t{i % 2}", duration=i) for i in range(1, 21)]
        rows.append(row("x", "t9", intent="订单", model="unknown", inp=None))

        groups = cost_report.cost_by_intent(rows, PRICES)

        assert groups["物流"]["requests"] == 2
        assert groups["物流"]["generations"] == 20
        assert groups["物流"]["p95_generation_ms"] == 19
        assert groups["物流"]["priced_subtotals"] == {"CNY": "0.120"}
        assert groups["物流"]["estimate_complete"] is True
        assert groups["订单"]["unknown_usage"] == 1
        assert groups["订单"]["unpriced"] == 1

    def test_duplicate_rows(self):
        a = row("g1", "t1")
        assert cost_report.cost_by_intent([a, dict(a)])["物流"]["generations"] == 1
        with pytest.raises(ValueError):
            cost_report.cost_by_intent([a, {**a, "intent": "订单"}])
        with pytest.raises(ValueError):
            cost_report.cost_by_intent([{**a, "trace_id": ""}])

    def test_make_cost_report_matches_schema(self):
        report = cost_report.make_cost_report(
            [row("g1", "t1"), row("g2", "t2", intent="订单", inp=10, out=10)], PRICES, source=" langfuse ",
        )

        CostReport.model_validate(report)
        assert report["meta"]["source"] == "langfuse"
        assert [r["intent"] for r in report["rows"]] == ["物流", "订单"]
        assert report["summary"]["requests"] == 2
        assert report["summary"]["estimate_complete"] is True

    def test_make_cost_report_requires_source(self):
        with pytest.raises(ValueError):
            cost_report.make_cost_report([], source=" ")
