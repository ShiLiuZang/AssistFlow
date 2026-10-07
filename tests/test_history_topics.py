"""
测试历史会话归类的隔离存储
覆盖数据持久化、多标签统计和非法标签拒绝
"""
import sqlite3

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


@pytest.mark.parametrize("fail", [False, True])
def test_history_topics_closes_connections_after_use(tmp_path, monkeypatch, fail):
    """写入、查ID和读取记录在成功或异常后都释放真实SQLite连接。"""
    monkeypatch.setattr(history_topics, "DB_PATH", tmp_path / "topics.sqlite")
    connect = sqlite3.connect
    connections = []

    def track_connection(*args, **kwargs):
        db = connect(*args, **kwargs)
        connections.append(db)
        return db

    monkeypatch.setattr(history_topics.sqlite3, "connect", track_connection)
    row = {"message_id": 1, "labels": ["物流"]}
    if fail:
        # 缺少text使写入在建立连接后失败；读取缺表数据库也必须关闭连接。
        with pytest.raises(KeyError, match="text"):
            history_topics.save([row])
        db = connect(history_topics.DB_PATH)
        try:
            db.execute("DROP TABLE history_topic_classifications")
            db.commit()
        finally:
            db.close()
        for read in (history_topics.existing_ids, history_topics.distribution):
            with pytest.raises(sqlite3.OperationalError, match="no such table"):
                read()
    else:
        assert history_topics.save([{**row, "text": "查物流"}]) == 1
        assert history_topics.existing_ids() == {1}
        assert history_topics.distribution()["total"] == 1

    assert len(connections) == 3
    for db in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            db.execute("SELECT 1")
