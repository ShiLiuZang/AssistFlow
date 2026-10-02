"""/api/kb：知识库总览、切块预览、录入查重、向量化、检索自测与对话暂存审核（MySQL/Milvus 为替身）。"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api import kb
from app.kb import documents
from app.kb.sources import SOURCE_TYPES

FAQ = "# 退货\n签收后7天内可无理由退货。\n# 运费\n质量问题运费由商家承担。\n"


@pytest.fixture
def milvus(monkeypatch):
    state = SimpleNamespace(has=True, count=4, error=None)

    class Client:
        def has_collection(self, name):
            if state.error:
                raise state.error
            return state.has

    async def acall(work):
        return work()

    monkeypatch.setattr(kb.milvus_client, "get_client", Client)
    monkeypatch.setattr(kb.milvus_client, "acall", acall)
    monkeypatch.setattr(kb.milvus_client, "count", lambda client: state.count)
    return state


@pytest.fixture
def kb_repo(repo, monkeypatch):
    repo.set("list_chunk_pairs", return_value=[])
    repo.set("knowledge_stats", return_value={"total": 4, "pending": 0, "done": 4, "by_content_type": {}, "key_clause": 1})
    repo.set("list_recent_chunks", return_value=[])
    repo.set("staging_stats", return_value={"kept": 1})
    repo.write = AsyncMock(return_value=[11, 12])
    repo.vectorize = AsyncMock(return_value=2)
    monkeypatch.setattr(kb.dualwrite, "write_pending", repo.write)
    monkeypatch.setattr(kb.dualwrite, "vectorize_pending", repo.vectorize)
    monkeypatch.setattr(kb.jobs, "status", lambda name, with_log=False: {"name": name})
    return repo


class TestHelpers:
    def test_fingerprint_normalizes(self):
        assert kb._fingerprint("退货 期限？", "7天") == kb._fingerprint("退货期限", "7天")

    def test_features(self):
        chunk = lambda path, answer: documents.Chunk(  # noqa: E731
            category="c", questions="q", answer=answer, section_path=path, content_type="faq", is_key_clause=0,
        )
        table = "| a | b |\n| - | - |\n| 1 | 2 |"
        features = kb._features([chunk("A", "x"), chunk("A", "y"), chunk("B", table), chunk("B", table), chunk("C", "z")])
        assert features == {"sections": 3, "table_split": True, "overlap": True, "multi_piece_sections": ["A", "B"]}

    async def test_milvus_state(self, milvus):
        assert (await kb.milvus_state())["count"] == 4
        milvus.has = False
        assert (await kb.milvus_state())["count"] == 0
        milvus.error = ConnectionError("refused")
        state = await kb.milvus_state()
        assert (state["online"], state["detail"]) == (False, "ConnectionError: refused")

    async def test_existing_fingerprints(self, repo):
        repo.set("list_chunk_pairs", return_value=[("q", "a")])
        assert await kb._existing_fingerprints() == {kb._fingerprint("q", "a")}
        repo.list_chunk_pairs.side_effect = RuntimeError()
        assert await kb._existing_fingerprints() is None


class TestOverview:
    def test_consistent(self, client, kb_repo, milvus):
        kb_repo.list_recent_chunks.return_value = [SimpleNamespace(
            id=1, questions="q", answer="a" * 200, category="c", section_path="p", content_type="faq",
            is_key_clause=1, vectorize_status="done", created_at=datetime(2026, 1, 1),
        )]
        body = client.get("/api/kb/overview").json()
        assert body["consistent"] is True
        assert len(body["recent"][0]["answer"]) == 120
        assert body["staging"] == {"kept": 1}
        assert {s["file"] for s in body["sources"]} == set(SOURCE_TYPES)
        assert all(s["present"] and s["chunks"] > 0 for s in body["sources"])
        assert [j["name"] for j in body["jobs"]] == list(kb.KB_JOBS)

    def test_database_down(self, client, kb_repo, milvus):
        kb_repo.knowledge_stats.side_effect = RuntimeError("no mysql")
        body = client.get("/api/kb/overview").json()
        assert (body["db_error"], body["consistent"], body["staging"]) == ("RuntimeError: no mysql", None, None)

    def test_staging_table_missing_and_mismatch(self, client, kb_repo, milvus):
        kb_repo.staging_stats.side_effect = RuntimeError()
        milvus.count = 3
        body = client.get("/api/kb/overview").json()
        assert (body["staging"], body["consistent"]) == (None, False)


class TestPreview:
    def test_text_with_duplicates(self, client, kb_repo):
        kb_repo.list_chunk_pairs.return_value = [("退货", "签收后7天内可无理由退货。")]
        body = client.post("/api/kb/preview", json={"text": FAQ + "# 退货\n签收后7天内可无理由退货。\n"}).json()
        assert (body["source"], body["total"], body["duplicates"], body["dedup_known"]) == ("手工录入", 3, 2, True)
        assert [c["duplicate"] for c in body["chunks"]] == [True, False, True]

    def test_dedup_unknown_without_mysql(self, client, kb_repo):
        kb_repo.list_chunk_pairs.side_effect = RuntimeError()
        body = client.post("/api/kb/preview", json={"text": FAQ}).json()
        assert body["dedup_known"] is False
        assert {c["duplicate"] for c in body["chunks"]} == {None}

    def test_source_file(self, client, kb_repo):
        body = client.post("/api/kb/preview", json={"file": "returns-policy.md"}).json()
        assert (body["source"], body["content_type"]) == ("data/kb/returns-policy.md", "policy")

    @pytest.mark.parametrize(
        "body,status",
        [
            ({"file": "../.env"}, 400),
            ({"text": "   "}, 400),
            ({"text": "x" * (kb.MAX_TEXT_CHARS + 1)}, 400),
            ({"text": "x", "content_type": "novel"}, 400),
        ],
    )
    def test_rejects(self, client, kb_repo, body, status):
        assert client.post("/api/kb/preview", json=body).status_code == status

    def test_missing_source_file(self, client, kb_repo, monkeypatch, tmp_path):
        monkeypatch.setattr(kb, "KB_DIR", tmp_path)
        assert client.post("/api/kb/preview", json={"file": "product-faq.md"}).status_code == 404


class TestIngestAndVectorize:
    def test_ingest_skips_duplicates_and_vectorizes(self, client, kb_repo, milvus):
        kb_repo.list_chunk_pairs.return_value = [("退货", "签收后7天内可无理由退货。")]
        kb_repo.write.return_value = [11]

        body = client.post("/api/kb/ingest", json={"text": FAQ}).json()

        assert (body["chunks"], body["inserted"], body["skipped"], body["vectorized"]) == (2, 1, 1, 2)
        written, = kb_repo.write.await_args.args
        assert [c.questions for c in written] == ["运费"]

    def test_ingest_without_vectorize(self, client, kb_repo, milvus):
        body = client.post("/api/kb/ingest", json={"text": FAQ, "vectorize": False}).json()
        assert body["vectorized"] is None
        kb_repo.vectorize.assert_not_awaited()

    def test_all_duplicates_write_nothing(self, client, kb_repo, milvus):
        kb_repo.list_chunk_pairs.return_value = [("退货", "签收后7天内可无理由退货。"), ("运费", "质量问题运费由商家承担。")]
        assert client.post("/api/kb/ingest", json={"text": FAQ}).json()["inserted"] == 0
        kb_repo.write.assert_not_awaited()

    @pytest.mark.parametrize(
        "setup,text,status",
        [
            (lambda r: None, "# 只有标题\n", 400),
            (lambda r: setattr(r.list_chunk_pairs, "side_effect", RuntimeError()), FAQ, 503),
            (lambda r: setattr(r.vectorize, "side_effect", ConnectionError()), FAQ, 502),
        ],
    )
    def test_ingest_errors(self, client, kb_repo, milvus, setup, text, status):
        setup(kb_repo)
        assert client.post("/api/kb/ingest", json={"text": text}).status_code == status

    def test_vectorize(self, client, kb_repo, milvus):
        assert client.post("/api/kb/vectorize").json()["vectorized"] == 2
        kb_repo.vectorize.side_effect = RuntimeError("embed down")
        assert client.post("/api/kb/vectorize").status_code == 502


class TestSearch:
    def test_projects_fields(self, client, monkeypatch):
        search = AsyncMock(return_value=[{"id": 1, "question": "q", "answer": "a", "score": 0.5, "secret": "x"}])
        monkeypatch.setattr(kb.retrieval, "search_knowledge", search)

        body = client.post("/api/kb/search", json={"q": " 退货 ", "strategy": "bm25", "top_k": 3}).json()

        assert body["q"] == "退货"
        assert "secret" not in body["hits"][0]
        assert search.await_args.args == ("退货",)
        assert search.await_args.kwargs == {"strategy": "bm25", "top_k": 3}

    @pytest.mark.parametrize("body,status", [({"q": " "}, 400), ({"q": "x", "strategy": "x"}, 400), ({"q": "x", "top_k": 21}, 422)])
    def test_validation(self, client, body, status):
        assert client.post("/api/kb/search", json=body).status_code == status

    def test_failure(self, client, monkeypatch):
        monkeypatch.setattr(kb.retrieval, "search_knowledge", AsyncMock(side_effect=RuntimeError()))
        assert client.post("/api/kb/search", json={"q": "x"}).status_code == 502


def staging_row(row_id, question="能退吗", answer="签收后7天内可退"):
    return SimpleNamespace(id=row_id, batch_no="b1", source_ref="returns-policy.md", question=question, answer=answer)


class TestStaging:
    def test_list(self, client, kb_repo):
        kb_repo.set("list_staging_by_status", return_value=[staging_row(1, answer="x" * 300)])
        body = client.get("/api/kb/staging", params={"limit": 1}).json()
        assert body["stats"] == {"kept": 1}
        assert body["limit"] == 1
        assert set(body["rows"]) == {"extracted", "kept", "discarded", "approved", "rejected"}
        assert [len(rows) for rows in body["rows"].values()] == [1] * 5
        assert len(body["rows"]["kept"][0]["answer"]) == 160
        kb_repo.list_staging_by_status.assert_awaited_with("rejected", limit=1)

    def test_list_limit_bounds(self, client):
        assert client.get("/api/kb/staging", params={"limit": 0}).status_code == 422
        assert client.get("/api/kb/staging", params={"limit": 101}).status_code == 422

    def test_list_unavailable(self, client, kb_repo):
        kb_repo.staging_stats.side_effect = RuntimeError()
        assert client.get("/api/kb/staging").status_code == 503

    @pytest.fixture
    def staged(self, kb_repo, monkeypatch):
        kb_repo.set("list_staging_by_ids", return_value=[staging_row(1), staging_row(2, "运费谁出", "退货运费买家承担")])
        kb_repo.set("set_staging_status")
        kb_repo.validated = []
        monkeypatch.setattr(kb, "validate_review_source", lambda *args: kb_repo.validated.append(args))
        return kb_repo

    def test_approve_writes_mined_chunks(self, client, staged):
        assert client.post("/api/kb/staging/approve", json={"ids": [1, 2]}).json() == {"approved": 2, "chunk_ids": [11, 12]}
        chunks, = staged.write.await_args.args
        assert {(c.content_type, c.section_path, c.category) for c in chunks} == {("mined", "mined", "历史对话")}
        assert [c.is_key_clause for c in chunks] == [documents.is_key("能退吗", "签收后7天内可退"), 1]
        assert staged.list_staging_by_ids.await_args.kwargs == {"status": "kept"}
        staged.set_staging_status.assert_awaited_once_with([1, 2], "approved")
        assert len(staged.validated) == 2

    def test_approve_requires_trusted_source(self, client, staged, monkeypatch):
        def untrusted(*args):
            raise ValueError("材料里找不到")

        monkeypatch.setattr(kb, "validate_review_source", untrusted)
        assert client.post("/api/kb/staging/approve", json={"ids": [1]}).status_code == 422
        staged.write.assert_not_awaited()

    def test_approve_write_failure_keeps_status(self, client, staged):
        staged.vectorize.side_effect = ConnectionError()
        assert client.post("/api/kb/staging/approve", json={"ids": [1]}).status_code == 502
        staged.set_staging_status.assert_not_awaited()

    @pytest.mark.parametrize("action", ["approve", "reject"])
    def test_already_processed_409(self, client, staged, action):
        staged.list_staging_by_ids.return_value = []
        assert client.post(f"/api/kb/staging/{action}", json={"ids": [1]}).status_code == 409

    @pytest.mark.parametrize("action", ["approve", "reject"])
    def test_empty_ids_422(self, client, staged, action):
        assert client.post(f"/api/kb/staging/{action}", json={"ids": []}).status_code == 422

    def test_reject(self, client, staged):
        assert client.post("/api/kb/staging/reject", json={"ids": [1, 2]}).json() == {"rejected": 2}
        staged.set_staging_status.assert_awaited_once_with([1, 2], "rejected")
