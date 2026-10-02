"""scripts.create_staff：员工账号命令行（仓储与引擎均为替身）。"""
from unittest.mock import AsyncMock

import pytest

from app.core import auth
from scripts import create_staff


@pytest.fixture
def saved(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr(create_staff.repository, "upsert_staff_user", upsert)
    monkeypatch.setattr(create_staff, "engine", type("E", (), {"dispose": AsyncMock()})())
    return upsert


def test_creates_hashed_account(saved, monkeypatch):
    monkeypatch.setenv("STAFF_PASSWORD", "longenough")
    assert create_staff.main(["--username", " alice ", "--role", "reviewer"]) == 0
    username, password_hash, role, active = saved.await_args.args
    assert (username, role, active) == ("alice", "reviewer", True)
    assert auth.verify_password("longenough", password_hash)


def test_disable(saved, monkeypatch):
    monkeypatch.setenv("STAFF_PASSWORD", "longenough")
    create_staff.main(["--username", "bob", "--role", "agent", "--disable"])
    assert saved.await_args.args[3] is False


@pytest.mark.parametrize("argv,password", [
    (["--username", "a", "--role", "agent"], "short"),
    (["--username", " ", "--role", "agent"], "longenough"),
])
def test_rejects(saved, monkeypatch, argv, password):
    monkeypatch.setenv("STAFF_PASSWORD", password)
    with pytest.raises(SystemExit):
        create_staff.main(argv)
    saved.assert_not_awaited()


def test_interactive_mismatch(saved, monkeypatch):
    monkeypatch.delenv("STAFF_PASSWORD", raising=False)
    answers = iter(["longenough", "different"])
    monkeypatch.setattr(create_staff.getpass, "getpass", lambda prompt: next(answers))
    with pytest.raises(SystemExit):
        create_staff.main(["--username", "a", "--role", "agent"])


def test_staff_create_is_not_a_web_job():
    from app.core.jobs import JOBS
    from scripts.tasks import MODULES

    assert MODULES["staff-create"] == "scripts.create_staff"
    assert "staff-create" not in JOBS
