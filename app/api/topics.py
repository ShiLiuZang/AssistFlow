"""
主题分类API路由模块

本模块提供用户问题的主题分布查询接口，供飞轮优化使用。
核心功能包括：查询权威类目定义、统计各主题问题数量、按主题分页查询问题列表。
在系统中充当主题分析的数据接口，帮助运营人员识别知识盲区并优先补充。
分布接口返回每类前3个样例，详情接口支持分页查看全部归类结果。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.core.taxonomy import TOPIC_CLASSES, TOPIC_NAMES
from app.core import topic_views
from app.core.auth import current_staff

router = APIRouter(dependencies=[Depends(current_staff)])


@router.get("/api/topics/catalog")
async def catalog() -> dict:
    """
    获取权威主题类目定义

    返回:
        包含status和classes字段的字典，每个类目包含label和boundary

    返回硬编码的主题类目列表，不依赖数据库
    类目定义来自app/core/taxonomy.py，包含17个标准类别
    boundary字段描述该类目的边界和典型问题
    """
    return {
        "status": "catalog",
        "classes": [
            {"label": item.name, "boundary": item.boundary}
            for item in TOPIC_CLASSES
        ],
    }


@router.get("/api/topics/distribution")
async def distribution():
    """
    获取主题分布统计

    返回:
        包含各主题问题数量和前3个样例的字典

    核心逻辑：
    1. 查询topic_classifications表统计各主题问题数
    2. 为每个主题返回最多3个样例问题
    3. 按问题数量降序排列

    边界情况：
    - 表未迁移或无数据时返回503，提示运行分类脚本

    供飞轮后台识别哪些主题问题多、需要优先补充知识
    """
    try:
        return await topic_views.distribution()
    except SQLAlchemyError as exc:
        raise HTTPException(503, "主题归类表未迁移，历史会话隔离归类尚未运行") from exc


@router.get("/api/topics/questions")
async def questions(
    label: str = Query(description="权威类目名,须在 17 类之内"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    按主题分页查询问题列表

    参数:
        label: 主题类目名（必须是17个标准类目之一）
        page: 页码，从1开始
        size: 每页数量，1-100之间

    返回:
        包含items、total、page、size的分页结果

    核心逻辑：
    1. 校验label是否在权威类目中
    2. 查询该主题下的所有问题
    3. 按页返回结果

    边界情况：
    - label不在权威类目中时返回400
    - 表未迁移或无数据时返回503

    供运营人员深入查看某个主题下的所有问题，决定如何补充知识
    """
    # 校验类目名
    if label not in TOPIC_NAMES:
        raise HTTPException(400, f"未知类目「{label}」,权威类目共 {len(TOPIC_NAMES)} 类")

    try:
        return await topic_views.questions(label, page=page, size=size)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "主题归类表未迁移，历史会话隔离归类尚未运行") from exc
