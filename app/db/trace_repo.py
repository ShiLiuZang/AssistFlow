"""工具审计、追踪记录和评估结果存储。"""

from sqlalchemy import select
from app.db import database
from sqlalchemy.exc import IntegrityError
from app.db.models import (
    ToolAuditLog, TraceSpan, EvalRun,
)
from app.tools.audit import ToolAuditRecord


async def insert_tool_audit(record: ToolAuditRecord) -> None:
    """
    插入工具审计日志

    参数:
        record: 工具审计记录

    设计说明:
        - 基于audit_key幂等：重复插入相同key的记录不报错
        - 记录工具调用的性能、状态、重试次数等
        - 用于工具使用分析和故障诊断
    """
    row = ToolAuditLog(
        audit_key=record.audit_key,
        tool_call_id=record.tool_call_id,
        conversation_id=record.conversation_id,
        tool_name=record.tool_name,
        source=record.source,
        server=record.server,
        status=record.status,
        duration_ms=record.duration_ms,
        retry_count=record.retry_count,
        argument_fields=list(record.argument_fields),
        result_chars=record.result_chars,
        created_at=record.created_at,
    )

    try:
        async with database.SessionLocal() as session, session.begin():
            session.add(row)
    except IntegrityError:
        if record.audit_key is None:
            raise



        async with database.SessionLocal() as session:
            existing_id = await session.scalar(
                select(ToolAuditLog.id).where(
                    ToolAuditLog.audit_key == record.audit_key,
                )
            )
        if existing_id is None:
            raise


async def insert_trace_span(payload: dict) -> None:
    """
    插入追踪span记录

    参数:
        payload: span数据字典

    设计说明:
        - 基于span_id幂等：重复插入相同span_id不报错
        - 记录trace的层级结构、性能、token使用量
        - 验证相同span_id的数据一致性
        - 用于可观测性分析和成本统计
    """
    values = {
        "span_id": payload["span_id"],
        "trace_id": payload["trace_id"],
        "parent_id": payload.get("parent_id"),
        "name": payload["name"],
        "status": payload["status"],
        "duration_ms": payload["duration_ms"],
        "error_type": payload.get("error_type"),
        "kind": payload.get("kind", "span"),
        "intent": payload.get("intent"),
        "model": payload.get("model"),
        "input_tokens": payload.get("input_tokens"),
        "output_tokens": payload.get("output_tokens"),
        "total_tokens": payload.get("total_tokens"),
    }

    try:
        async with database.SessionLocal() as session, session.begin():
            session.add(TraceSpan(**values))
    except IntegrityError:
        async with database.SessionLocal() as session:
            existing = await session.get(
                TraceSpan,
                values["span_id"],
            )

            if existing is None:
                raise

            if any(
                getattr(existing, key) != value
                for key, value in values.items()
            ):
                raise ValueError(
                    "相同 span_id 对应不同的观测记录"
                )


async def list_trace_spans(trace_id: str) -> list[dict]:
    """
    列出trace的所有span记录

    参数:
        trace_id: 追踪ID

    返回:
        span字典列表，按创建时间和span_id排序

    设计说明:
        用于trace详情查看和调试
    """
    async with database.SessionLocal() as session:
        statement = (
            select(TraceSpan)
            .where(TraceSpan.trace_id == trace_id)
            .order_by(
                TraceSpan.created_at,
                TraceSpan.span_id,
            )
        )
        rows = list(await session.scalars(statement))

        return [
            {
                "trace_id": row.trace_id,
                "span_id": row.span_id,
                "parent_id": row.parent_id,
                "name": row.name,
                "status": row.status,
                "duration_ms": row.duration_ms,
                "error_type": row.error_type,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


async def save_eval_run(report: dict) -> int:
    """
    保存评估运行报告

    参数:
        report: 评估报告字典

    返回:
        评估运行ID

    设计说明:
        记录评估指标用于持续改进
    """
    async with database.SessionLocal() as session:
        row = EvalRun(**report)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def list_eval_runs(limit: int = 10) -> list[dict]:
    """
    列出评估运行记录

    参数:
        limit: 返回数量上限

    返回:
        评估运行列表，按ID降序

    设计说明:
        用于评估历史查看和指标对比
    """
    async with database.SessionLocal() as session:
        rows = await session.scalars(
            select(EvalRun).order_by(EvalRun.id.desc()).limit(limit)
        )
        return [
            {
                "id": row.id,
                "dataset_version": row.dataset_version,
                "case_ids": row.case_ids,
                "config_version": row.config_version,
                "kb_revision": row.kb_revision,
                "strategy": row.strategy,
                "top_k": row.top_k,
                "triggered_by": row.triggered_by,
                "status": row.status,
                "metrics": row.metrics,
                "details": row.details,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
