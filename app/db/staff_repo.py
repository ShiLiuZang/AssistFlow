"""后台员工账号"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import StaffUser


async def get_staff_user(username: str) -> StaffUser | None:
    """按用户名读取员工账号；不存在返回 None。"""
    async with SessionLocal() as session:
        return await session.scalar(select(StaffUser).where(StaffUser.username == username))


async def touch_staff_login(user_id: int) -> None:
    """记录最近登录时间（UTC）。"""
    async with SessionLocal() as session:
        user = await session.get(StaffUser, user_id)
        if user is not None:
            user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()


async def upsert_staff_user(username: str, password_hash: str, role: str, active: bool = True) -> StaffUser:
    """创建员工账号；已存在时更新密码、角色和启用状态。"""
    async with SessionLocal() as session:
        user = await session.scalar(select(StaffUser).where(StaffUser.username == username))
        if user is None:
            user = StaffUser(username=username)
            session.add(user)
        user.password_hash = password_hash
        user.role = role
        user.active = active
        await session.commit()
        return user
