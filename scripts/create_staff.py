"""创建或更新后台员工账号：python -m scripts.tasks staff-create --username alice --role reviewer

密码从终端交互输入（不回显），也可以用环境变量 STAFF_PASSWORD 传入（便于自动化部署）。
"""
import argparse
import asyncio
import getpass
import os

from app.core.auth import ROLES, hash_password
from app.db import repository
from app.db.database import engine

MIN_PASSWORD_LENGTH = 8


def read_password() -> str:
    password = os.environ.get("STAFF_PASSWORD")
    if password is None:
        password = getpass.getpass("密码：")
        if getpass.getpass("再次输入密码：") != password:
            raise SystemExit("两次输入的密码不一致")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"密码至少 {MIN_PASSWORD_LENGTH} 位")
    return password


async def run(username: str, role: str, password: str, active: bool) -> None:
    try:
        await repository.upsert_staff_user(username, hash_password(password), role, active)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--disable", action="store_true", help="停用该账号（已签发的令牌在有效期内仍可用）")
    args = parser.parse_args(argv)
    username = args.username.strip()
    if not username or len(username) > 64:
        raise SystemExit("用户名长度需为 1 到 64 个字符")
    asyncio.run(run(username, args.role, read_password(), not args.disable))
    print(f"已保存账号 {username}（{args.role}{'，已停用' if args.disable else ''}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
