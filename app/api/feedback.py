from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import repository


router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    """反馈请求模型"""
    user_id: str
    conversation_id: int
    message_id: str
    rating: str  # "up" 或 "down"


@router.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest) -> dict:
    """提交用户反馈。

    只有 down 评分会落入问题池，up 评分不处理。
    会验证消息归属和会话归属，防止越权访问。
    """
    # 验证 rating 参数
    if request.rating not in {"up", "down"}:
        raise HTTPException(
            status_code=400,
            detail="rating 必须是 up 或 down",
        )

    # 验证会话归属
    conversation = await repository.get_conversation(
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
        pool_id = await repository.submit_feedback(
            owner=request.user_id,
            conversation=str(request.conversation_id),
            message_id=request.message_id,
            rating=request.rating,
        )

        if pool_id is None:
            # up 评分，不落池
            return {
                "success": True,
                "message": "感谢您的反馈",
                "pool_id": None,
            }
        else:
            # down 评分，已落池
            return {
                "success": True,
                "message": "感谢您的反馈，我们会尽快改进",
                "pool_id": pool_id,
            }

    except PermissionError:
        # 消息不属于该用户/会话
        raise HTTPException(
            status_code=403,
            detail="消息不存在或无权访问",
        )

    except ValueError as e:
        # 其他验证错误
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:
        # 未预期的错误
        raise HTTPException(
            status_code=500,
            detail="反馈提交失败",
        )
