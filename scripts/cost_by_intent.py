"""按意图统计已保存模型代次的用量并保存报表快照。"""

import asyncio
from decimal import Decimal
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import select

from app.core.cost_report import Price, make_cost_report
from app.db.database import SessionLocal
from app.db.models import TraceSpan
from app.schemas.cost_report import CostReport


REPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "09"
    / "reports"
    / "cost_by_intent.json"
)

# DeepSeek-V4.1-Flash，2026-09-10 起的高峰/输入缓存未命中档。
# 这里是保守参考估算；本地记录尚未保存缓存命中和实际计费时段。
# 价格来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
REFERENCE_PRICES = {
    "deepseek-flash": Price(
        input_per_million=Decimal("2"),
        output_per_million=Decimal("8"),
        currency="CNY",
        as_of="deepseek-v4.1-flash@2026-09-10:peak-cache-miss-reference",
    ),
}


async def load_generation_rows() -> list[dict]:
    async with SessionLocal() as session:
        generations = list(await session.scalars(
            select(TraceSpan)
            .where(TraceSpan.kind == "generation")
            .order_by(TraceSpan.created_at, TraceSpan.span_id)
        ))

        trace_ids = {row.trace_id for row in generations}
        intents = {}
        if trace_ids:
            classifications = list(await session.scalars(
                select(TraceSpan).where(
                    TraceSpan.trace_id.in_(trace_ids),
                    TraceSpan.name == "classify",
                )
            ))
            intents = {
                row.trace_id: row.intent
                for row in classifications
                if row.intent
            }

    return [
        {
            "trace_id": row.trace_id,
            "generation_id": row.span_id,
            "intent": (
                "后台摘要" if row.name == "summary_model"
                else intents.get(row.trace_id, "unknown")
            ),
            "model": row.model,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "duration_ms": row.duration_ms,
        }
        for row in generations
    ]


async def build_report() -> dict:
    rows = await load_generation_rows()
    report = make_cost_report(
        rows,
        prices=REFERENCE_PRICES,
        source="mysql.trace_spans",
    )
    return CostReport.model_validate(report).model_dump(mode="json")


def save_report(
    report: dict,
    path: Path = REPORT_PATH,
) -> None:
    content = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)

        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


async def main() -> None:
    report = await build_report()
    save_report(report)
    summary = report["summary"]
    print(
        f"已生成 {REPORT_PATH}："
        f"{summary['requests']} 次请求，"
        f"{summary['generations']} 次模型生成。"
    )


if __name__ == "__main__":
    asyncio.run(main())
