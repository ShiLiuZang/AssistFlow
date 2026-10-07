"""
管理后台总览API路由模块

本模块提供管理后台首页的卡片式总览接口，聚合各子系统的健康状态。
核心功能包括：知识库状态、RAG评估、飞轮审核队列、可观测性数据、主题分布、分类器验收。
在系统中充当运维和监控的统一入口，让管理员快速了解系统各模块的运行状况。
每个卡片包含：状态（ok/attention/missing/error）、指标、提示信息。
"""

import json
from pathlib import Path

from app.core.auth import require_admin

from fastapi import Depends, APIRouter
from sqlalchemy import func, select

from app.api import acceptance, kb, observability
from app.api.knowledge import REPORT_PATH
from app.config import settings
from app.db import knowledge_repo, topic_repo
from app.db.database import SessionLocal
from app.db.models import Review


router = APIRouter(dependencies=[Depends(require_admin)], prefix="/api/admin")


def _card(key: str, title: str, page: str, lede: str) -> dict:
    """
    创建标准卡片结构

    参数:
        key: 卡片唯一标识
        title: 卡片标题
        page: 跳转页面路径
        lede: 简短描述

    返回:
        包含默认字段的卡片字典

    所有卡片函数都基于此模板构建，确保结构一致
    默认状态为error，各函数根据实际情况修改
    """
    return {"key": key, "title": title, "page": page, "lede": lede,
            "status": "error", "headline": "读数失败", "metrics": [], "note": None}


async def _kb_card() -> dict:
    """
    生成知识库状态卡片

    返回:
        知识库卡片字典

    核心逻辑：
    1. 从数据库读取知识块统计（总数、待向量化、关键条款）
    2. 查询Milvus向量库状态和数量
    3. 比对MySQL与Milvus的数量一致性
    4. 根据状态设置卡片状态：
       - 无知识块：missing
       - Milvus离线：attention
       - 数量不一致或有待向量化：attention
       - 数量一致：ok

    边界情况：
    - 数据库读取失败时返回error状态

    为什么需要双端校验：
    MySQL存储原文和元数据，Milvus存储向量
    两端数量一致才能保证检索正常工作
    """
    card = _card("kb", "知识库", "/kb", "材料切块、录入、向量化与检索自测")
    try:
        stats = await knowledge_repo.knowledge_stats()
        milvus = await kb.milvus_state()
    except Exception:
        card["note"] = "知识库统计读取失败，请检查数据库结构与连接。"
        return card
    card["metrics"] = [
        {"label": "知识块", "value": stats["total"]},
        {"label": "待向量化", "value": stats["pending"]},
        {"label": "Milvus", "value": milvus["count"] if milvus["online"] else "离线"},
        {"label": "关键条款", "value": stats["key_clause"]},
    ]
    if stats["total"] == 0:
        card["status"], card["headline"] = "missing", "知识库尚无知识块"
    elif not milvus["online"]:
        card["status"], card["headline"] = "attention", "MySQL 有原文，Milvus 当前离线"
    elif stats["pending"] or stats["done"] != milvus["count"]:
        card["status"], card["headline"] = "attention", "知识块仍待向量化或两端数量不一致"
    else:
        card["status"], card["headline"] = "ok", "知识块与向量数量一致"
    card["note"] = "数量一致仅是状态检查，检索质量需在知识库页自测。"
    return card


def _rag_card() -> dict:
    """
    生成RAG评估报告卡片

    返回:
        RAG评估卡片字典

    核心逻辑：
    1. 读取评估报告JSON文件
    2. 提取各策略的MRR（平均倒数排名）指标
    3. 找出MRR最高的策略
    4. 展示策略数、评估题数、最佳MRR

    边界情况：
    - 文件不存在：missing
    - 文件损坏：error
    - 报告状态非evaluated：missing
    - 缺少MRR数据：error

    MRR是检索质量的核心指标，值越接近1越好
    """
    card = _card("rageval", "RAG 评估", "/rag-eval", "读取已保存的检索评估报告")
    try:
        report = json.loads(Path(REPORT_PATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        card["status"], card["headline"] = "missing", "尚未生成真实评估报告"
        return card
    except (OSError, UnicodeError, ValueError):
        card["note"] = "报告读取或解析失败。"
        return card
    if report.get("status") != "evaluated":
        card["status"], card["headline"] = "missing", "尚无完整评估结果"
        return card
    summary = report.get("summary") or {}
    scored = [(name, values.get("mrr")) for name, values in summary.items()
              if isinstance(values, dict) and isinstance(values.get("mrr"), (int, float))]
    if not scored:
        card["note"] = "报告缺少可比较的 MRR 数据。"
        return card
    best, mrr = max(scored, key=lambda item: item[1])
    card["status"], card["headline"] = "ok", f"{best} 的 MRR 最高：{mrr:.3f}"
    card["metrics"] = [
        {"label": "策略数", "value": len(scored)},
        {"label": "评估题数", "value": summary[best].get("cases", "—")},
        {"label": "最佳 MRR", "value": f"{mrr:.3f}"},
    ]
    card["note"] = f"报告生成于 {report.get('created_at', '未知时间')}，页面只读报告。"
    return card


async def _review_card() -> dict:
    """
    生成飞轮审核队列卡片

    返回:
        审核队列卡片字典

    核心逻辑：
    1. 按状态分组统计reviews表记录数
    2. 展示待审、发布中、已通过、已驳回的数量
    3. 根据待审和发布中的数量设置状态：
       - 无记录：missing
       - 有待处理：attention
       - 无待处理：ok

    边界情况：
    - 表读取失败：error

    飞轮流程：低置信度问题 -> 待审 -> 发布中 -> 已通过/已驳回
    """
    card = _card("review", "飞轮待审队列", "/review", "低置信度问题归并、人工审核与定向发布")
    try:
        async with SessionLocal() as session:
            counts = dict((await session.execute(
                select(Review.status, func.count()).group_by(Review.status)
            )).all())
    except Exception:
        card["note"] = "审核队列读取失败，请检查数据库迁移与连接。"
        return card
    pending = counts.get("pending", 0)
    publishing = counts.get("publishing", 0)
    card["metrics"] = [
        {"label": "待审", "value": pending},
        {"label": "发布中", "value": publishing},
        {"label": "已通过", "value": counts.get("approved", 0)},
        {"label": "已驳回", "value": counts.get("rejected", 0)},
    ]
    if not counts:
        card["status"], card["headline"] = "missing", "审核队列尚无记录"
    elif pending or publishing:
        card["status"], card["headline"] = "attention", f"{pending} 条待审，{publishing} 条待完成发布"
    else:
        card["status"], card["headline"] = "ok", "当前没有待审或发布中的记录"
    card["note"] = "可在审核页查看原话并核准；操作会记录审核人名称。"
    return card


async def _observability_card() -> dict:
    """
    生成可观测性数据卡片

    返回:
        可观测性卡片字典

    核心逻辑：
    1. 调用observability.overview获取三项数据：
       - 成本报表：模型调用次数和费用
       - 评估趋势：固定集复评轮次
       - 置信度校准：在用阈值
    2. 统计缺失项
    3. 根据就绪情况设置状态：
       - 三项均缺失：missing
       - 部分缺失：attention
       - 全部就绪：ok

    边界情况：
    - 数据读取失败：error

    这三项是系统运行质量的关键指标
    """
    card = _card("observability", "观测与成本", "/observability",
                 "读取模型成本、固定集复评与置信度校准的真实记录")
    try:
        data = await observability.overview()
    except Exception:
        card["note"] = "观测数据读取失败。"
        return card
    cost, trend, calibration = data["cost"], data["trend"], data["calibration"]
    runs = trend.get("runs") or []
    card["metrics"] = [
        {"label": "模型调用", "value": (cost.get("summary") or {}).get("generations", "—")},
        {"label": "可比评估轮次", "value": len(runs) if trend["status"] == "ok" else "—"},
        {"label": "在用阈值", "value": f"{settings.evidence_min_confidence:.2f}"},
    ]
    missing = [name for name, block in (("成本报表", cost), ("评估趋势", trend),
                                        ("阈值校准", calibration)) if block["status"] != "ok"]
    if len(missing) == 3:
        card["status"], card["headline"] = "missing", "三项观测数据均未就绪"
    elif missing:
        card["status"], card["headline"] = "attention", "待补：" + "、".join(missing)
    else:
        card["status"], card["headline"] = "ok", "三项观测数据已就绪"
    card["note"] = "缺失项显示未就绪，不以零值冒充结果。"
    return card


async def _topics_card() -> dict:
    """
    生成主题分布卡片

    返回:
        主题分布卡片字典

    核心逻辑：
    1. 查询topic_classifications表的统计数据
    2. 统计总问题数和命中的类目数
    3. 根据是否有数据设置状态

    边界情况：
    - 表读取失败：error
    - 无数据：missing
    - 有数据：ok

    主题分布用于识别知识盲区，决定优先补充哪些领域的知识
    """
    card = _card("topics", "主题分布", "/topics", "旁路分类结果中的 17 类问题分布")
    try:
        dist = await topic_repo.topic_distribution()
    except Exception:
        card["note"] = "主题归类表读取失败，请检查 微调 迁移与数据库连接。"
        return card
    hit = sum(item["count"] > 0 for item in dist["classes"])
    card["metrics"] = [
        {"label": "已归类问题", "value": dist["total"]},
        {"label": "命中类目", "value": f"{hit}/{len(dist['classes'])}"},
    ]
    if dist["total"]:
        card["status"], card["headline"] = "ok", f"已归类 {dist['total']} 条问题"
    else:
        card["status"], card["headline"] = "missing", "还没有旁路归类结果"
    return card


async def _classifier_card() -> dict:
    """
    生成分类器验收卡片

    返回:
        分类器验收卡片字典

    核心逻辑：
    1. 调用acceptance.overview获取九项验收结果
    2. 统计通过项数和在线状态
    3. 根据验收情况设置状态：
       - 全部通过：ok
       - 有失败项：attention
       - 缺产物：missing

    边界情况：
    - 产物读取失败：error

    九项验收包括：语料构建、数据集划分、模型训练、评估指标等
    """
    card = _card("classifier", "分类器验收", "/acceptance", "Minihelp 微调 九项实证")
    try:
        result = await acceptance.overview()
    except Exception:
        card["note"] = "分类器产物读取失败。"
        return card
    passed, total = result["passed"], result["total"]
    online = result["classifier"]["online"]
    card["metrics"] = [
        {"label": "验收通过", "value": f"{passed}/{total}"},
        {"label": "分类服务", "value": "在线" if online else "离线"},
    ]
    if result["all_pass"]:
        card["status"], card["headline"] = "ok", "九项验收全部通过"
    else:
        missing = sum(item["status"] == "missing" for item in result["blocks"])
        failed = sum(item["status"] == "fail" for item in result["blocks"])
        card["status"] = "attention" if failed else "missing"
        card["headline"] = f"{missing} 项缺产物，{failed} 项未过线"
    card["note"] = "只读本项目 data/finetune 的产物；源码复制不等于模型已训练。"
    return card


@router.get("/overview")
async def overview() -> dict:
    """
    获取管理后台总览数据

    返回:
        包含modules字段的字典，modules为卡片列表

    聚合六个子系统的状态卡片，供前端渲染仪表板
    卡片按功能重要性排序：知识库 > 评估 > 审核 > 监控 > 主题 > 分类器
    """
    return {"modules": [
        await _kb_card(),
        _rag_card(),
        await _review_card(),
        await _observability_card(),
        await _topics_card(),
        await _classifier_card(),
    ]}
