"""
用户反馈API路由模块

本模块提供用户对AI回复进行点赞/点踩的反馈接口。
核心功能：接收用户评分、校验权限、将差评消息加入问题池供后续改进。
在系统中充当用户反馈收集的入口，为飞轮优化提供数据源。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import current_customer

from app.db import conversation_repo, flywheel_repo


router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    """
    反馈请求模型

    属性:
        user_id: 已废弃，身份取自令牌
        conversation_id: 会话ID
        message_id: 消息ID（AI消息的turn_message_id）
        rating: 评分，up（点赞）或down（点踩）
    """
    user_id: str | None = Field(default=None, description="已废弃：身份取自令牌，此字段会被忽略")
    conversation_id: int
    message_id: str
    rating: str


@router.post("/api/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    user_id: str = Depends(current_customer),
) -> dict:
    """
    提交用户反馈

    参数:
        request: FeedbackRequest对象

    返回:
        包含success、message、pool_id的字典

    核心逻辑：
    1. 校验rating字段只能是up或down
    2. 校验会话存在性和所属权
    3. 调用flywheel_repo.submit_feedback提交反馈
    4. 如果是down评分，返回问题池ID；up评分不处理

    边界情况：
    - rating非法时返回400
    - 会话不存在或无权访问时返回404
    - 消息不存在或无权访问时返回403（flywheel_repo 抛出 PermissionError）
    - 其他参数错误时返回400
    - 未知异常时返回500

    为什么只处理down评分：
    差评代表用户不满意，需要收集到问题池进行分析和改进
    点赞只作为正向信号记录，不需要进入改进流程
    """
    request.user_id = user_id  # 身份只来自令牌
    # 校验rating字段
    if request.rating not in {"up", "down"}:
        raise HTTPException(
            status_code=400,
            detail="rating 必须是 up 或 down",
        )

    # 校验会话存在性和所属权
    conversation = await conversation_repo.get_conversation(
        request.conversation_id,
        request.user_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在或无权访问",
        )

    try:
        # 提交反馈
        pool_id = await flywheel_repo.submit_feedback(
            owner=request.user_id,
            conversation=str(request.conversation_id),
            message_id=request.message_id,
            rating=request.rating,
        )

        if pool_id is None:
            # up评分，不加入问题池
            return {
                "success": True,
                "message": "感谢您的反馈",
                "pool_id": None,
            }
        else:
            # down评分，已加入问题池
            return {
                "success": True,
                "message": "感谢您的反馈，我们会尽快改进",
                "pool_id": pool_id,
            }

    except PermissionError:
        # 消息不存在或无权访问
        raise HTTPException(
            status_code=403,
            detail="消息不存在或无权访问",
        )

    except ValueError as e:
        # 参数错误
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:
        # 未知异常
        raise HTTPException(
            status_code=500,
            detail="反馈提交失败",
        )
