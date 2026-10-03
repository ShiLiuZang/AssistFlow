"""本地数据源：主题类目、历史归类库（临时 SQLite）、主题视图降级、受信材料校验、后台作业。"""
import asyncio
import sys
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core import history_topics, jobs, taxonomy, topic_views
from app.kb import trusted_sources
from app.kb.sources import KB_DIR, SOURCE_TYPES


class TestTaxonomy:
    def test_tables_consistent(self):
        assert taxonomy.NUM_CLASSES == len(taxonomy.TOPIC_NAMES) == 17
        assert len(set(taxonomy.TOPIC_NAMES)) == taxonomy.NUM_CLASSES
        assert all(taxonomy.ID2LABEL[taxonomy.LABEL2ID[name]] == name for name in taxonomy.TOPIC_NAMES)
        assert set(taxonomy.SEVERITY.values()) == {"严", "中", "宽"}

    def test_terminology_table_lists_every_class(self):
        lines = taxonomy.terminology_table().splitlines()
        assert len(lines) == taxonomy.NUM_CLASSES
        assert lines[0].startswith("- 退换货:")
        assert "示例:" in lines[0]


@pytest.fixture
def history_db(tmp_path, monkeypatch):
    path = tmp_path / "history.sqlite"
    monkeypatch.setattr(history_topics, "DB_PATH", path)
    return path


class TestHistoryTopics:
    def test_unavailable_without_db(self, history_db):
        assert history_topics.available() is False
        assert history_topics.existing_ids() == set()
        with pytest.raises(FileNotFoundError):
            history_topics.distribution()

    def test_save_is_idempotent(self, history_db):
        rows = [
            {"message_id": 1, "text": "到哪了", "labels": ["物流"], "asked_at": "2026-01-01"},
            {"message_id": 2, "text": "能退吗", "labels": ["退换货", "运费"]},
        ]
        assert history_topics.save(rows) == 2
        assert history_topics.save(rows) == 0
        assert history_topics.existing_ids() == {1, 2}

    def test_connections_are_closed(self, history_db, monkeypatch):
        import sqlite3

        opened = []
        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            opened.append(real_connect(*args, **kwargs))
            return opened[-1]

        monkeypatch.setattr(history_topics.sqlite3, "connect", connect)
        history_topics.save([{"message_id": 1, "text": "到哪了", "labels": ["物流"]}])
        history_topics.existing_ids()
        history_topics.distribution()

        assert len(opened) >= 3
        for db in opened:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                db.execute("SELECT 1")

    @pytest.mark.parametrize(
        "rows",
        [
            [{"message_id": 1, "text": "a", "labels": ["物流"]}, {"message_id": 1, "text": "b", "labels": ["物流"]}],
            [{"message_id": 1, "text": "a", "labels": []}],
            [{"message_id": 1, "text": "a", "labels": ["不存在"]}],
            [{"message_id": 1, "text": "a", "labels": ["物流", "物流"]}],
            [{"message_id": 1, "text": "a", "labels": "物流"}],
        ],
    )
    def test_save_rejects_invalid_rows(self, history_db, rows):
        with pytest.raises(ValueError):
            history_topics.save(rows)

    def test_distribution_and_questions(self, history_db):
        history_topics.save([
            {"message_id": i, "text": f"问题{i}", "labels": ["物流"] if i % 2 else ["物流", "运费"]}
            for i in range(1, 6)
        ])

        dist = history_topics.distribution(samples_per_class=2)
        counts = {c["label"]: c for c in dist["classes"]}
        assert dist["total"] == 5
        assert counts["物流"]["count"] == 5
        assert counts["物流"]["samples"] == ["问题1", "问题2"]
        assert counts["运费"]["count"] == 2
        assert len(dist["classes"]) == taxonomy.NUM_CLASSES

        page = history_topics.questions("物流", page=2, size=2)
        assert (page["total"], page["pages"], page["page"]) == (5, 3, 2)
        assert [item["question_id"] for item in page["items"]] == [3, 2]

        beyond = history_topics.questions("物流", page=99, size=2)
        assert beyond["page"] == 3
        assert history_topics.questions("发票")["pages"] == 1


class TestTopicViews:
    @pytest.fixture
    def repo(self, monkeypatch):
        dist = AsyncMock(return_value={"total": 3, "classes": []})
        questions = AsyncMock(return_value={"items": ["db"]})
        monkeypatch.setattr(topic_views.topic_repo, "topic_distribution", dist)
        monkeypatch.setattr(topic_views.topic_repo, "topic_questions", questions)
        return dist, questions

    @pytest.fixture
    def history(self, monkeypatch):
        monkeypatch.setattr(topic_views.history_topics, "available", lambda: True)
        monkeypatch.setattr(topic_views.history_topics, "distribution", lambda: {"source": "history"})
        monkeypatch.setattr(topic_views.history_topics, "questions", lambda label, page, size: {"source": "history"})

    async def test_business_table_preferred(self, repo, history):
        assert await topic_views.distribution() == {"total": 3, "classes": []}
        assert await topic_views.questions("物流", page=2, size=5) == {"items": ["db"]}
        repo[1].assert_awaited_once_with("物流", page=2, size=5)

    async def test_empty_business_table_falls_back(self, repo, history):
        repo[0].return_value = {"total": 0}
        assert await topic_views.distribution() == {"source": "history"}
        assert await topic_views.questions("物流") == {"source": "history"}

    async def test_db_error_falls_back(self, repo, history):
        repo[0].side_effect = SQLAlchemyError("no table")
        assert await topic_views.distribution() == {"source": "history"}

    async def test_db_error_without_history_raises(self, repo, monkeypatch):
        monkeypatch.setattr(topic_views.history_topics, "available", lambda: False)
        repo[0].side_effect = SQLAlchemyError("no table")
        with pytest.raises(SQLAlchemyError):
            await topic_views.distribution()
        with pytest.raises(SQLAlchemyError):
            await topic_views.questions("物流")


def source_quote(name):
    text = (KB_DIR / name).read_text(encoding="utf-8")
    line = next(line.strip() for line in text.splitlines() if len(line.strip()) > 10 and not line.startswith("#"))
    return line[:20]


class TestValidateReviewSource:
    def test_returns_digest_for_verbatim_quote(self):
        name = next(iter(SOURCE_TYPES))
        digest = trusted_sources.validate_review_source("退货流程", source_quote(name), name)
        assert len(digest) == 64

    @pytest.mark.parametrize(
        "question,answer,source,message",
        [
            (" ", "x", "product-faq.md", "标准问题"),
            ("ORD-123 能退吗", "x", "product-faq.md", "脱敏"),
            ("找 13812345678", "x", "product-faq.md", "脱敏"),
            ("发到 a@b.com", "x", "product-faq.md", "脱敏"),
            ("q", "x", "../secret.md", "白名单"),
            ("q", " ", "product-faq.md", "不能为空"),
            ("q", "这句话不在任何材料里ZZZ", "product-faq.md", "连续原文"),
        ],
    )
    def test_rejections(self, question, answer, source, message):
        with pytest.raises(ValueError, match=message):
            trusted_sources.validate_review_source(question, answer, source)


@pytest.fixture
def quick_jobs(tmp_path, monkeypatch):
    """把作业表换成秒级完成的 Python 命令，日志写到临时目录。"""
    monkeypatch.setattr(jobs, "LOG_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_runs", {})
    monkeypatch.setattr(jobs, "JOBS", {
        "ok": jobs.JobSpec("ok", "成功作业", (sys.executable, "-c", "print('hello')"), "无"),
        "fail": jobs.JobSpec("fail", "失败作业", (sys.executable, "-c", "raise SystemExit(3)"), "无"),
        "slow": jobs.JobSpec("slow", "慢作业", (sys.executable, "-c", "import time; time.sleep(30)"), "无", heavy=True),
    })


class TestJobs:
    def test_registry_uses_tasks_module(self):
        assert all(spec.argv[1:3] == ("-m", "scripts.tasks") for spec in jobs.JOBS.values())

    async def test_successful_run(self, quick_jobs):
        run = await jobs.start("ok")
        assert run.status == "running"
        await run.watcher

        status = jobs.status("ok", with_log=True)
        assert (status["status"], status["returncode"]) == ("ok", 0)
        assert "hello" in status["log"]
        assert status["log"].startswith("$ ")

    async def test_failed_run(self, quick_jobs):
        await (await jobs.start("fail")).watcher
        assert jobs.status("fail")["status"] == "failed"
        assert jobs.status("fail")["returncode"] == 3

    async def test_cannot_start_twice_and_stop(self, quick_jobs):
        run = await jobs.start("slow")
        with pytest.raises(RuntimeError, match="正在运行"):
            await jobs.start("slow")

        await jobs.stop("slow")
        await asyncio.wait_for(run.watcher, 5)
        assert jobs.status("slow")["status"] == "stopped"

    async def test_stop_when_idle(self, quick_jobs):
        with pytest.raises(RuntimeError, match="没有在运行"):
            await jobs.stop("ok")

    def test_status_before_any_run(self, quick_jobs):
        status = jobs.status("ok", with_log=True)
        assert (status["status"], status["log"], status["log_mtime"]) == ("idle", "", None)
        assert [s["name"] for s in jobs.status_all()] == ["ok", "fail", "slow"]

    def test_tail_limits_lines(self, quick_jobs):
        jobs.log_path("ok").write_text("\n".join(str(i) for i in range(10)), encoding="utf-8")
        assert jobs.tail("ok", lines=3) == "7\n8\n9"
