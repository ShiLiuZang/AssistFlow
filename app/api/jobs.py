"""
后台作业管理API路由模块

本模块提供后台作业的启动、停止、状态查询接口。
核心功能：管理长时间运行的后台任务（如知识库构建、分类器训练），供管理页面调用。
在系统中充当后台作业的统一入口，将作业名映射到具体的命令执行。
作业定义和参数配置在app/core/jobs.py中维护。
"""

from app.core.auth import require_admin

from fastapi import Depends, APIRouter, HTTPException

from app.core import jobs

router = APIRouter(dependencies=[Depends(require_admin)], prefix="/api/jobs")


def _known(name: str) -> None:
    """
    校验作业名是否已注册

    参数:
        name: 作业名

    抛出:
        HTTPException 404: 作业名未在jobs.JOBS中注册

    作为统一的白名单校验，防止执行未授权的命令
    """
    if name not in jobs.JOBS:
        raise HTTPException(status_code=404, detail=f"未注册的作业:{name}")


@router.get("")
async def jobs_list() -> dict:
    """
    获取所有作业的状态列表

    返回:
        包含jobs字段的字典，每个作业包含name、status、pid等信息

    供管理页面展示所有后台作业的运行状态
    """
    return {"jobs": jobs.status_all()}


@router.post("/{name}")
async def job_start(name: str) -> dict:
    """
    启动指定作业

    参数:
        name: 作业名（路径参数）

    返回:
        作业状态字典，包含status、pid、log等字段

    核心逻辑：
    1. 校验作业名是否已注册
    2. 调用jobs.start启动作业
    3. 返回作业状态和日志尾部

    边界情况：
    - 作业未注册时返回404
    - 作业已在运行时返回409（RuntimeError）
    - 命令无法启动时返回500（FileNotFoundError）
    """
    _known(name)
    try:
        await jobs.start(name)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"命令起不来:{e}") from e
    return jobs.status(name, with_log=True)


@router.get("/{name}")
async def job_status(name: str) -> dict:
    """
    查询指定作业的状态

    参数:
        name: 作业名（路径参数）

    返回:
        作业状态字典，包含status、pid、log等字段

    供前端轮询作业执行进度
    """
    _known(name)
    return jobs.status(name, with_log=True)


@router.post("/{name}/stop")
async def job_stop(name: str) -> dict:
    """
    停止指定作业

    参数:
        name: 作业名（路径参数）

    返回:
        作业状态字典

    核心逻辑：
    1. 校验作业名是否已注册
    2. 调用jobs.stop停止作业
    3. 返回最新状态

    边界情况：
    - 作业未注册时返回404
    - 作业未在运行时返回409（RuntimeError）
    """
    _known(name)
    try:
        await jobs.stop(name)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return jobs.status(name, with_log=True)
