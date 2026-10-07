"""
可观测性仪表板API路由模块

本模块提供系统可观测性数据的聚合接口，包括成本报告、评测趋势和置信度校准。
核心功能包括：读取成本报表、加载评测运行历史、读取置信度校准报告、计算分布统计。
在系统中充当监控和优化的数据源，供运维人员和开发人员评估系统运行状况和性能趋势。
"""

import asyncio
import logging
import json
from pathlib import Path

from app.core.auth import require_admin

from fastapi import Depends, APIRouter
from pydantic import ValidationError

from app.schemas.cost_report import CostReport
from app.config import settings
from app.core.flywheel_evaluation import comparable
from app.db import trace_repo

router = APIRouter(
    dependencies=[Depends(require_admin)],
    prefix="/api/observability",
    tags=["observability"],
)

logger = logging.getLogger(__name__)

# 成本报告文件路径
COST_REPORT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "09"
    / "reports"
    / "cost_by_intent.json"
)

# 校准报告文件路径
CALIBRATION_PATH = COST_REPORT_PATH.with_name("calibration.json")


def unavailable(hint: str) -> dict:
    """
    生成不可用状态的响应字典

    参数:
        hint: 提示信息

    返回:
        标准格式的不可用响应

    统一的错误响应格式，便于前端展示占位状态
    """
    return {
        "present": False,
        "status": "not_integrated",
        "hint": hint,
        "can_run": False,
    }


def read_cost_report() -> dict:
    """
    读取成本报告文件

    返回:
        成本报告字典，包含present、status、hint、rows等字段

    核心逻辑：
    1. 尝试读取并校验成本报告JSON文件
    2. 如果文件不存在，返回missing状态
    3. 如果读取或校验失败，返回error状态
    4. 如果报告为空（无模型调用记录），标记为missing
    5. 成功时返回报告内容和ok状态

    边界情况：
    - 文件不存在、读取失败、格式错误统一处理
    - 报告存在但为空时给出提示
    """
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
    """
    计算数值列表的分布统计

    参数:
        values: 数值列表

    返回:
        包含n、min、p25、p50、p75、max的字典

    计算五数概括（最小值、四分位数、中位数、最大值）
    用于展示置信度分数的分布情况
    """
    ordered = sorted(values)

    def at(p: float) -> float | None:
        """获取指定百分位的值"""
        if not ordered:
            return None
        return ordered[round((len(ordered) - 1) * p)]

    return {
        "n": len(ordered),
        "min": at(0), "p25": at(0.25), "p50": at(0.5),
        "p75": at(0.75), "max": at(1),
    }


def read_calibration() -> dict:
    """
    读取置信度校准报告

    返回:
        校准报告字典，包含推荐阈值、分布统计、使用状态等字段

    核心逻辑：
    1. 读取校准报告JSON文件
    2. 校验报告完整性（必须有scan和scored字段）
    3. 分别提取answerable和absent两类样本的分数
    4. 计算两类样本的分数分布
    5. 比对推荐阈值与当前配置是否同步

    边界情况：
    - 文件不存在时返回missing状态
    - 格式错误或缺少必要字段时返回error状态
    - 两类样本有任一为空时视为不完整

    为什么需要这个函数：
    置信度阈值直接影响拒答率和答案质量，需要基于真实数据校准
    此接口展示校准结果和当前配置的同步状态
    """
    try:
        report = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))

        # 校验报告完整性
        if report.get("status") != "ok" or not report.get("scan") or not report.get("scored"):
            raise ValueError("incomplete calibration report")

        scored = report["scored"]

        # 分离可回答和不可回答样本的分数
        answerable = [row["score"] for row in scored if row["answerable"]]
        absent = [row["score"] for row in scored if not row["answerable"]]

        # 确保两类样本都存在
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
        "in_use": settings.evidence_min_confidence,  # 当前使用的阈值
        "in_sync": report["recommended"]["threshold"] == settings.evidence_min_confidence,  # 是否与推荐值同步
        "distribution": {
            "answerable": _distribution(answerable),
            "absent": _distribution(absent),
        },
    }


async def read_trend() -> dict:
    """
    读取评测趋势数据

    返回:
        评测趋势字典，包含可比较的评测运行列表和指标名称

    核心逻辑：
    1. 从数据库加载所有评测运行记录
    2. 选择最新一次运行作为基准
    3. 过滤出与基准可比较的运行（数据集、策略、配置相同）
    4. 返回可比较运行列表和指标名称

    边界情况：
    - 数据库读取失败时返回error状态
    - 无评测记录时返回missing状态
    - 不可比较的运行被省略，记录省略数量

    为什么需要可比较性判断：
    评测结果只有在条件相同时才能比较趋势，否则会产生误导
    """
    try:
        # 加载所有评测运行记录
        runs = await trace_repo.list_eval_runs()
    except Exception:
        logger.exception("评测运行记录读取失败")
        return {"present": False, "status": "error", "hint": "评测运行记录读取失败。", "can_run": False}

    if not runs:
        return {"present": False, "status": "missing", "hint": "尚未运行固定集复评。", "can_run": False}

    # 使用最新运行作为基准
    latest = runs[0]

    # 过滤出可比较的运行
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
    """
    获取可观测性总览数据

    返回:
        包含cost、trend、calibration三部分的字典

    聚合三个独立的数据源，供前端渲染可观测性仪表板
    使用asyncio.to_thread将同步IO操作转为异步，避免阻塞事件循环
    """
    return {
        "cost": await asyncio.to_thread(read_cost_report),
        "trend": await read_trend(),
        "calibration": await asyncio.to_thread(read_calibration),
    }
