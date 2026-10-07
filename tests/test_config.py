"""配置卫生：临时 env、无值泄露的告警及示例字段同步。"""
import asyncio
import logging
from pathlib import Path
import runpy
from unittest.mock import AsyncMock

from dotenv import dotenv_values
from pydantic import ValidationError
import pytest

from app.config import Settings, settings, warn_unknown_env_keys


def test_unknown_env_keys_warn_without_values(tmp_path, caplog, monkeypatch):
    env_file = tmp_path / "test.env"
    env_file.write_text(
        '# 注释不属于配置键\n'
        'CHAT_MODEL="known-secret"\n'
        'export CHECKPOINTER_DB_PATH="private-checkpoint-path"\n'
        'CHAT_API_KEEY="private-api-key\nsecond-secret-line"\n'
        'EMPTY_UNKNOWN=\n'
        'BARE_UNKNOWN\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PROCESS_ONLY_SETTING", "private-process-value")

    with caplog.at_level(logging.WARNING, logger="app.config"):
        warn_unknown_env_keys(env_file)

    assert caplog.record_tuples == [
        ("app.config", logging.WARNING,
         "未知配置键：BARE_UNKNOWN, CHAT_API_KEEY, CHECKPOINTER_DB_PATH, EMPTY_UNKNOWN"),
    ]
    for value in ("known-secret", "private-checkpoint-path", "private-api-key",
                  "second-secret-line", "private-process-value", "PROCESS_ONLY_SETTING"):
        assert value not in caplog.text


def test_known_env_keys_are_case_insensitive_and_silent(tmp_path, caplog):
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "chat_model=test-model\nGrApH_ChEcKpOiNt_PaTh=test.sqlite\n"
        "CLASSIFIER_URL=http://classifier.example\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="app.config"):
        warn_unknown_env_keys(env_file)

    assert not caplog.records


def test_missing_env_file_is_silent(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        warn_unknown_env_keys(tmp_path / "missing.env")

    assert not caplog.records


def test_startup_warns_before_external_services(tmp_path, monkeypatch, caplog):
    from app import main

    env_file = tmp_path / "test.env"
    env_file.write_text("CHECKPOINTER_DB_PATH=private-startup-value\n", encoding="utf-8")
    monkeypatch.setattr(main, "warn_unknown_env_keys", lambda: warn_unknown_env_keys(env_file))
    discover = AsyncMock(side_effect=RuntimeError("stop before external services"))
    monkeypatch.setattr(main, "make_services_with_mcp", discover)

    async def start():
        async with main.lifespan(main.app):
            pytest.fail("startup should stop at the mocked service discovery")

    with caplog.at_level(logging.WARNING, logger="app.config"):
        with pytest.raises(RuntimeError, match="stop before external services"):
            asyncio.run(start())

    discover.assert_awaited_once()
    assert caplog.messages == ["未知配置键：CHECKPOINTER_DB_PATH"]
    assert "private-startup-value" not in caplog.text


def test_mysql_database_url_is_required(monkeypatch):
    monkeypatch.delenv("MYSQL_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)

    assert [(error["loc"], error["type"]) for error in exc.value.errors()] == [
        (("mysql_database_url",), "missing"),
    ]


def test_classifier_url_loads_from_temporary_env(tmp_path, monkeypatch):
    monkeypatch.delenv("CLASSIFIER_URL", raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text("CLASSIFIER_URL=http://classifier.example:8123/custom/\n", encoding="utf-8")

    config = Settings(_env_file=env_file)

    assert config.classifier_url == "http://classifier.example:8123/custom/"
    assert config.mysql_database_url == "sqlite+aiosqlite:///:memory:"


@pytest.mark.parametrize("source, variable, suffix", [
    ("app/api/acceptance.py", "CLASSIFIER", ""),
    ("scripts/finetune/classify_history.py", "SERVICE", ""),
    ("scripts/finetune/classify_pool.py", "SERVICE", ""),
    ("scripts/finetune/scan_threshold_replay.py", "SERVICE", "/classify"),
])
def test_classifier_consumers_use_configured_url(monkeypatch, source, variable, suffix):
    monkeypatch.setattr(settings, "classifier_url", "http://classifier.example:8123/custom/")
    root = Path(__file__).resolve().parents[1]

    namespace = runpy.run_path(str(root / source))

    assert namespace[variable] == f"http://classifier.example:8123/custom{suffix}"


def test_env_example_keys_match_settings():
    root = Path(__file__).resolve().parents[1]
    example = dotenv_values(root / ".env.example", interpolate=False)

    assert set(example) == {name.upper() for name in Settings.model_fields}
    assert example["MILVUS_URI"] == Settings.model_fields["milvus_uri"].default
