"""Web v2 新增的只读接口：知识块分页与详情、候选问答详情、问题池统计、审核材料、分页审核队列。"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from tests.api.test_operations import review_row

QUOTE = "自签收之日起 7 天内,商品完好、不影响二次销售的,支持无理由退货。"


def chunk_row(chunk_id=1, answer="签收后7天内可退", **extra):
    data = dict(
        id=chunk_id, questions="能退吗", answer=answer, category="退货", section_path="退货/无理由",
        content_type="policy", is_key_clause=1, vectorize_status="done", created_at=datetime(2026, 10, 2, 8, 30),
        vector_id="v1", review_id=None, prev_chunk_id=None, next_chunk_id=2,
    )
    data.update(extra)
    return SimpleNamespace(**data)


class TestChunks:
    def test_page_truncates_answer(self, client, repo):
        repo.set("list_knowledge_chunks", return_value={"items": [chunk_row(answer="x" * 300)], "total": 1, "page": 2, "size": 5})
        body = client.get("/api/kb/chunks", params={"page": 2, "size": 5, "q": "退", "status": "done", "content_type": "policy"}).json()
        assert repo.list_knowledge_chunks.await_args.kwargs == {"page": 2, "size": 5, "q": "退", "status": "done", "content_type": "policy"}
        item, = body["items"]
        assert (len(item["answer"]), item["answer_chars"], item["is_key_clause"]) == (160, 300, True)
        assert item["created_at"] == "2026-10-02T08:30:00"
        assert "vector_id" not in item and body["total"] == 1

    @pytest.mark.parametrize("params", [{"page": 0}, {"size": 101}, {"status": "x"}, {"content_type": "x"}])
    def test_rejects_bad_params(self, client, params):
        assert client.get("/api/kb/chunks", params=params).status_code == 422

    def test_unavailable(self, client, repo):
        repo.set("list_knowledge_chunks", side_effect=RuntimeError())
        assert client.get("/api/kb/chunks").status_code == 503

    def test_detail_has_full_answer_and_links(self, client, repo):
        repo.set("get_knowledge_chunk", return_value=chunk_row(answer="x" * 300, created_at=None))
        body = client.get("/api/kb/chunks/1").json()
        assert (len(body["answer"]), body["vector_id"], body["next_chunk_id"], body["created_at"]) == (300, "v1", 2, None)

    def test_detail_missing_and_unavailable(self, client, repo):
        repo.set("get_knowledge_chunk", return_value=None)
        assert client.get("/api/kb/chunks/1").status_code == 404
        repo.get_knowledge_chunk.side_effect = RuntimeError()
        assert client.get("/api/kb/chunks/1").status_code == 503
        assert client.get("/api/kb/chunks/0").status_code == 422


def staging_row(source_ref="returns-policy.md", answer=QUOTE):
    return SimpleNamespace(id=5, question="无理由退货几天", answer=answer, status="kept", source_ref=source_ref,
                           batch_no="mine-1-abc", created_at=datetime(2026, 10, 2))


class TestStagingDetail:
    def test_valid_quote(self, client, repo):
        repo.set("list_staging_by_ids", return_value=[staging_row()])
        body = client.get("/api/kb/staging/5").json()
        assert repo.list_staging_by_ids.await_args.args == ([5],)
        material = body["material"]
        assert (material["status"], material["valid"]) == ("available", True)
        assert len(material["sha256"]) == 64 and QUOTE in material["text"]

    def test_quote_not_in_material(self, client, repo):
        repo.set("list_staging_by_ids", return_value=[staging_row(answer="编造的条款")])
        material = client.get("/api/kb/staging/5").json()["material"]
        assert (material["status"], material["valid"]) == ("available", False)
        assert material["reason"]

    @pytest.mark.parametrize("source_ref,status", [(None, "missing"), ("../../etc/passwd", "untrusted")])
    def test_untrusted_sources_are_not_read(self, client, repo, source_ref, status):
        repo.set("list_staging_by_ids", return_value=[staging_row(source_ref=source_ref)])
        material = client.get("/api/kb/staging/5").json()["material"]
        assert (material["status"], material["text"]) == (status, None)

    def test_missing_and_unavailable(self, client, repo):
        repo.set("list_staging_by_ids", return_value=[])
        assert client.get("/api/kb/staging/5").status_code == 404
        repo.list_staging_by_ids.side_effect = RuntimeError()
        assert client.get("/api/kb/staging/5").status_code == 503


class TestReviewReads:
    def test_stats(self, client, repo):
        repo.set("flywheel_stats", return_value={"pool": 3, "pending_review": 1})
        assert client.get("/api/review/stats").json() == {"pool": 3, "pending_review": 1}
        repo.flywheel_stats.side_effect = RuntimeError()
        assert client.get("/api/review/stats").status_code == 503

    def test_material_whitelist(self, client):
        body = client.get("/api/review/materials/returns-policy.md").json()
        assert QUOTE in body["text"] and len(body["sha256"]) == 64
        assert client.get("/api/review/materials/secret.md").status_code == 404

    def test_paged_queue(self, client, repo):
        repo.set("review_queue_page", return_value={"items": [review_row()], "total": 1, "page": 1, "size": 20})
        body = client.get("/api/review/queue", params={"status": "待审", "page": 1, "q": "退"}).json()
        assert repo.review_queue_page.await_args.args == ("pending",)
        assert repo.review_queue_page.await_args.kwargs == {"page": 1, "size": 20, "q": "退"}
        assert body["items"][0]["review_status"] == "待审" and body["total"] == 1

    def test_paged_queue_unavailable(self, client, repo):
        repo.set("review_queue_page", side_effect=RuntimeError())
        assert client.get("/api/review/queue", params={"page": 1}).status_code == 503
