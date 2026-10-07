"""公开的匿名访客身份签发入口。"""
import secrets

from fastapi import APIRouter

from app.core.auth import issue_visitor_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/visitor")
async def create_visitor() -> dict[str, str | int]:
    user_id = "v_" + secrets.token_hex(16)
    token, expires_at = issue_visitor_token(user_id)
    return {"user_id": user_id, "token": token, "expires_at": expires_at}
