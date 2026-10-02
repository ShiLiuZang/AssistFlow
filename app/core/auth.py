"""
认证与授权

两套互不通用的身份：
- 顾客：电商主站在顾客登录后用 CUSTOMER_TOKEN_SECRET 签发 JWT（typ=customer, sub=顾客 ID），
  本服务只校验，不落库。开发模式下可以用 /api/auth/dev/customer-token 模拟签发。
- 员工：本服务 /api/auth/login 校验 staff_users 表后用 AUTH_SECRET 签发 JWT（typ=staff, sub=用户名, role）。

两类令牌用不同密钥签名，并校验 typ，顾客令牌不能当员工令牌用，反之亦然。
请求体或查询参数里的 user_id 一律不再采信，身份只来自这里的依赖。
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

Role = Literal["admin", "reviewer", "agent"]
ROLES: tuple[str, ...] = ("admin", "reviewer", "agent")
ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32

# 开发模式下未配置密钥时，进程内生成一次；重启后旧令牌全部失效
_dev_secrets: dict[str, str] = {}

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Staff:
    username: str
    role: str


class AuthConfigError(RuntimeError):
    """认证配置不满足上线要求。"""


def _secret(name: Literal["auth_secret", "customer_token_secret"]) -> str:
    value = getattr(settings, name).strip()
    if len(value) >= MIN_SECRET_LENGTH:
        return value
    if settings.auth_dev_mode:
        if name not in _dev_secrets:
            _dev_secrets[name] = secrets.token_urlsafe(48)
            logger.warning("开发模式：%s 未配置，已生成临时密钥，重启后令牌失效", name.upper())
        return _dev_secrets[name]
    raise AuthConfigError(f"{name.upper()} 未配置或少于 {MIN_SECRET_LENGTH} 字符")


def check_configuration() -> None:
    """应用启动时调用：非开发模式下两个密钥都必须配置，否则拒绝启动。"""
    _secret("auth_secret")
    _secret("customer_token_secret")
    if settings.auth_dev_mode:
        logger.warning("AUTH_DEV_MODE 已开启：任何人都能模拟顾客身份，切勿用于生产")


# ==================== 密码 ====================

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    """scrypt 哈希，格式 scrypt$盐$摘要（均为十六进制）。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex), dklen=32, **_SCRYPT,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# 用户不存在时也做一次同样耗时的校验，避免靠响应时间探测用户名
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


# ==================== 令牌 ====================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_staff_token(username: str, role: str) -> str:
    claims = {
        "typ": "staff", "sub": username, "role": role,
        "iat": _now(), "exp": _now() + timedelta(minutes=settings.staff_token_ttl_minutes),
    }
    return jwt.encode(claims, _secret("auth_secret"), algorithm=ALGORITHM)


def issue_customer_token(user_id: str, ttl_minutes: int = 120) -> str:
    """模拟电商主站签发顾客令牌；生产中由主站签发，本服务只在开发模式和测试中使用。"""
    claims = {"typ": "customer", "sub": user_id, "iat": _now(), "exp": _now() + timedelta(minutes=ttl_minutes)}
    return jwt.encode(claims, _secret("customer_token_secret"), algorithm=ALGORITHM)


def _decode(token: str, secret_name, expected_typ: str) -> dict:
    try:
        claims = jwt.decode(
            token, _secret(secret_name), algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("登录已失效，请重新登录") from exc
    if claims.get("typ") != expected_typ or not str(claims.get("sub", "")).strip():
        raise _unauthorized("令牌类型不正确")
    return claims


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def _token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("请先登录")
    return credentials.credentials


# ==================== FastAPI 依赖 ====================

async def current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """返回令牌里的顾客 ID。"""
    claims = _decode(_token(credentials), "customer_token_secret", "customer")
    return str(claims["sub"])


async def current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Staff:
    """返回令牌里的员工身份。角色在签发时写入，账号停用后令牌在有效期内仍可用。"""
    claims = _decode(_token(credentials), "auth_secret", "staff")
    role = claims.get("role")
    if role not in ROLES:
        raise _unauthorized("令牌角色无效")
    return Staff(username=str(claims["sub"]), role=role)


def require_roles(*roles: str):
    """限定角色的依赖；管理员总是放行。"""
    allowed = {"admin", *roles}

    async def dependency(staff: Staff = Depends(current_staff)) -> Staff:
        if staff.role not in allowed:
            raise HTTPException(403, "当前账号没有执行此操作的权限")
        return staff

    return dependency


require_admin = require_roles("admin")
require_reviewer = require_roles("reviewer")
