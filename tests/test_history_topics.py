"""
测试历史会话归类的隔离存储
覆盖数据持久化、多标签统计和非法标签拒绝
"""
import pytest

from app.core import history_topics


def test_history_topics_persists_source_and_multilabel_counts(tmp_path, monkeypatch):
    """测试历史归类：持久化到隔离库，统计多标签分布"""
    monkeypatch.setattr(history_topics, "DB_PATH", tmp_path / "topics.sqlite")
    rows = [
        {"message_id": 10, "text": "猫窝买大了想退", "labels": ["尺码", "退换货"],
         "asked_at": "2026-09-29T10:00:00"},
        {"message_id": 11, "text": "快递到哪了", "labels": ["物流"],
         "asked_at": "2026-09-29T10:01:00"},
    ]
    assert history_topics.save(rows) == 2
    assert history_topics.save(rows) == 0
    assert history_topics.existing_ids() == {10, 11}

    dist = history_topics.distribution()
    counts = {item["label"]: item["count"] for item in dist["classes"]}
    assert dist["source"] == "conversation_history" and dist["total"] == 2
    assert (counts["尺码"], counts["退换货"], counts["物流"]) == (1, 1, 1)

    page = history_topics.questions("退换货", page=1, size=1)
    assert page["source"] == "conversation_history" and page["total"] == 1
    assert page["items"][0]["question_id"] == 10
    assert page["items"][0]["source"] == "conversation_history"


def test_history_topics_rejects_invalid_labels(tmp_path, monkeypatch):
    """测试标签验证：拒绝不在术语表中的标签"""
    monkeypatch.setattr(history_topics, "DB_PATH", tmp_path / "topics.sqlite")
    with pytest.raises(ValueError):
        history_topics.save([{"message_id": 1, "text": "x", "labels": ["不在术语表"]}])
