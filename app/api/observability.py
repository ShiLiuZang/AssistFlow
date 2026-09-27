import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import ValidationError

from app.schemas.cost_report import CostReport

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


@router.get("/overview")
async def overview() -> dict:
    return {
        "cost": await asyncio.to_thread(read_cost_report),
        "trend": unavailable(
            "评测运行记录尚未接入，暂时无法展示趋势。"
        ),
        "calibration": unavailable(
            "置信度计算与阈值校准任务尚未接入。"
        ),
    }
