import asyncio
import logging
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import ValidationError

from app.schemas.cost_report import CostReport
from app.config import settings
from app.core.flywheel_evaluation import comparable
from app.db import repository

router = APIRouter(
    prefix="/api/observability",
    tags=["observability"],
)

logger = logging.getLogger(__name__)
COST_REPORT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "09"
    / "reports"
    / "cost_by_intent.json"
)
CALIBRATION_PATH = COST_REPORT_PATH.with_name("calibration.json")

def unavailable(hint: str) -> dict:
    return {
        "present": False,
        "status": "not_integrated",
        "hint": hint,
        "can_run": False,
    }


def read_cost_report() -> dict:
    try:
        content = COST_REPORT_PATH.read_text(encoding="utf-8")
        report = CostReport.model_validate_json(content)
    except FileNotFoundError:
        return {
            "present": False,
            "status": "missing",
            "hint": "尚未生成成本报表。",
            "can_run": False,
        }
    except (OSError, UnicodeError, ValidationError):
        logger.warning("成本报表读取或格式校验失败")
        return {
            "present": False,
            "status": "error",
            "hint": "成本报表读取失败或格式不正确，请检查报表文件。",
            "can_run": False,
        }

    return {
        **report.model_dump(mode="json"),
        "present": bool(report.rows),
        "status": "ok" if report.rows else "missing",
        "hint": None if report.rows else "报表已生成，但输入数据中没有模型调用记录。",
        "can_run": False,
    }


def _distribution(values: list[float]) -> dict:
    ordered = sorted(values)

    def at(p: float) -> float | None:
        if not ordered:
            return None
        return ordered[round((len(ordered) - 1) * p)]

    return {
        "n": len(ordered),
        "min": at(0), "p25": at(0.25), "p50": at(0.5),
        "p75": at(0.75), "max": at(1),
    }


def read_calibration() -> dict:
    try:
        report = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        if report.get("status") != "ok" or not report.get("scan") or not report.get("scored"):
            raise ValueError("incomplete calibration report")
        scored = report["scored"]
        answerable = [row["score"] for row in scored if row["answerable"]]
        absent = [row["score"] for row in scored if not row["answerable"]]
        if not answerable or not absent:
            raise ValueError("calibration classes missing")
    except FileNotFoundError:
        return {"present": False, "status": "missing", "hint": "尚未运行真实校准脚本。", "can_run": False}
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("校准报告读取或格式校验失败")
        return {"present": False, "status": "error", "hint": "校准报告损坏或读取失败。", "can_run": False}
    return {
        **report,
        "present": True,
        "status": "ok",
        "can_run": False,
        "in_use": settings.evidence_min_confidence,
        "in_sync": report["recommended"]["threshold"] == settings.evidence_min_confidence,
        "distribution": {
            "answerable": _distribution(answerable),
            "absent": _distribution(absent),
        },
    }


async def read_trend() -> dict:
    try:
        runs = await repository.list_eval_runs()
    except Exception:
        logger.exception("评测运行记录读取失败")
        return {"present": False, "status": "error", "hint": "评测运行记录读取失败。", "can_run": False}
    if not runs:
        return {"present": False, "status": "missing", "hint": "尚未运行固定集复评。", "can_run": False}
    latest = runs[0]
    comparable_runs = [run for run in runs if comparable(latest, run)]
    return {
        "present": True,
        "status": "ok",
        "can_run": False,
        "runs": comparable_runs,
        "metric_names": ["recall_at_k", "mrr", "refusal_accuracy", "faithfulness"],
        "omitted_incomparable": len(runs) - len(comparable_runs),
        "hint": "仅比较数据集、题目、策略、配置版本和 K 相同的运行。",
    }


@router.get("/overview")
async def overview() -> dict:
    return {
        "cost": await asyncio.to_thread(read_cost_report),
        "trend": await read_trend(),
        "calibration": await asyncio.to_thread(read_calibration),
    }
