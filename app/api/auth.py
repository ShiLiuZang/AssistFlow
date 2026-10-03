"""
认证接口

- POST /api/auth/login：员工登录，返回员工令牌
- GET  /api/auth/me：当前员工身份
- POST /api/auth/dev/customer-token：开发模式下模拟电商主站签发顾客令牌，生产返回 404
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core import auth
from app.core.ratelimit import check_login_account, limit_login
from app.db import repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class DevCustomerIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w.-]+$")


@router.post("/login", dependencies=[Depends(limit_login)])
async def login(body: LoginIn, request: Request) -> dict:
    """校验账号密码并签发员工令牌；失败时不区分用户名错还是密码错。"""
    check_login_account(request, body.username)
    try:
        user = await repository.get_staff_user(body.username.strip())
    except Exception as exc:
        logger.exception("读取员工账号失败")
        raise HTTPException(503, "账号服务暂时不可用") from exc

    stored = user.password_hash if user is not None else auth.DUMMY_PASSWORD_HASH
    valid = auth.verify_password(body.password, stored)
    if user is None or not valid or not user.active or user.role not in auth.ROLES:
        raise HTTPException(401, "用户名或密码错误")

    try:
        await repository.touch_staff_login(user.id)
    except Exception:
        logger.warning("记录登录时间失败 user=%s", user.username)
    return {
        "access_token": auth.issue_staff_token(user.username, user.role),
        "token_type": "bearer",
        "expires_in": settings.staff_token_ttl_minutes * 60,
        "username": user.username,
        "role": user.role,
    }


@router.get("/me")
async def me(staff: auth.Staff = Depends(auth.current_staff)) -> dict:
    return {"username": staff.username, "role": staff.role}


@router.get("/config")
async def config() -> dict:
    """前端据此决定是否显示「模拟顾客」入口。"""
    return {"dev_mode": settings.auth_dev_mode}


@router.post("/dev/customer-token")
async def dev_customer_token(body: DevCustomerIn) -> dict:
    if not settings.auth_dev_mode:
        raise HTTPException(404, "Not Found")
    return {"access_token": auth.issue_customer_token(body.user_id), "token_type": "bearer", "user_id": body.user_id}
