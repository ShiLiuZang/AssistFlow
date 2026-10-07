"""匿名访客签名令牌与管理员 Bearer 鉴权。"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)
_process_secret: bytes | None = None


def _signing_key() -> bytes:
    global _process_secret
    if settings.auth_secret:
        return settings.auth_secret.encode("utf-8")
    if _process_secret is None:
        _process_secret = secrets.token_bytes(32)
        logger.warning("未配置 AUTH_SECRET，使用进程随机密钥；重启后访客令牌失效")
    return _process_secret


def initialize_auth() -> None:
    """启动时初始化签名密钥；随机密钥仅保存在当前进程。"""
    _signing_key()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(decoded) != value:
        raise ValueError("非法 base64url")
    return decoded


def issue_visitor_token(user_id: str) -> tuple[str, int]:
    """返回 (token, expires_at)，身份由服务端提供。"""
    if not user_id:
        raise ValueError("user_id 不能为空")
    expires_at = int(time.time()) + settings.visitor_token_ttl_days * 86400
    payload = _encode(json.dumps({"sub": user_id, "exp": expires_at}, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_encode(signature)}", expires_at


def verify_visitor_token(token: str) -> str:
    """校验签名、载荷与过期时间；失败抛出 ValueError。"""
    try:
        payload, signature = token.split(".")
        expected = hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_decode(signature), expected):
            raise ValueError("无效签名")
        data = json.loads(_decode(payload))
        if (
            not isinstance(data, dict)
            or set(data) != {"sub", "exp"}
            or not isinstance(data["sub"], str)
            or not data["sub"]
            or type(data["exp"]) is not int
            or data["exp"] <= time.time()
        ):
            raise ValueError("无效或过期的载荷")
        return data["sub"]
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("无效或过期的访客令牌") from exc


def _unauthorized() -> HTTPException:
    return HTTPException(401, "缺失、无效或过期的令牌", headers={"WWW-Authenticate": "Bearer"})


def _bearer(authorization: str | None) -> str:
    parts = (authorization or "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _unauthorized()
    return parts[1]


def require_visitor(authorization: str | None = Header(default=None)) -> str:
    """读取 Authorization: Bearer，返回经过验证的 user_id。"""
    try:
        return verify_visitor_token(_bearer(authorization))
    except ValueError as exc:
        raise _unauthorized() from exc


def require_admin(authorization: str | None = Header(default=None)) -> None:
    """空配置返回 503；缺失或错误的管理员令牌返回 401。"""
    if not settings.admin_token:
        raise HTTPException(503, "未配置 ADMIN_TOKEN")
    supplied = _bearer(authorization)
    if not hmac.compare_digest(supplied.encode("utf-8"), settings.admin_token.encode("utf-8")):
        raise _unauthorized()


def resolve_visitor_id(visitor_id: str, claimed_user_id: str | None) -> str:
    """兼容旧请求中的身份字段，但只信任令牌身份。"""
    if claimed_user_id is not None and claimed_user_id != visitor_id:
        raise HTTPException(403, "user_id 与访客令牌不一致")
    return visitor_id
