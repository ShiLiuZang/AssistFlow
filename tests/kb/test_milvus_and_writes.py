"""Milvus 封装、双写向量化、审核发布与对话挖掘。Milvus 客户端、嵌入、MySQL 均为替身。"""
from unittest.mock import AsyncMock

import pytest

from app.kb import dualwrite, milvus_client, mining, review_publish
from app.kb.documents import Chunk
from app.kb.sources import KB_DIR, SOURCE_TYPES
from tests.helpers import FakeStructuredModel, patch_model


def raw_hit(hit_id, distance=0.5):
    return {
        "id": hit_id,
        "distance": distance,
        "entity": {
            "question": f"q{hit_id}", "answer": f"a{hit_id}", "section_path": "p",
            "content_type": "faq", "category": "c",
        },
    }


class Recorder:
    """吸收 schema / index 构造调用。"""

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class FakeMilvus:
    def __init__(self, exists=True, fields=None):
        self.exists = exists
        self.fields = fields if fields is not None else [
            {"name": "dense", "params": {"dim": milvus_client.DIM}},
            {"name": "sparse"},
            {"name": "text"},
        ]
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            # 实例上覆盖的处理函数优先，其次是类里定义的 _<name> 方法
            handler = self.__dict__.get(f"_{name}")
            if handler is None:
                method = getattr(type(self), f"_{name}", None)
                handler = method.__get__(self) if method else (lambda *a, **k: None)
            return handler(*args, **kwargs)
        return record

    def _create_schema(self, **kwargs):
        return Recorder()

    def _prepare_index_params(self):
        return Recorder()

    def _has_collection(self, name):
        return self.exists

    def _describe_collection(self, name):
        return {"fields": self.fields}

    def _search(self, **kwargs):
        return [[raw_hit(1, 0.9), raw_hit(2, 0.3)]]

    def _hybrid_search(self, **kwargs):
        return [[raw_hit(3)]]

    def _query(self, **kwargs):
        return [{"count(*)": 42}]

    def names(self):
        return [name for name, _, _ in self.calls]


class TestMilvusClient:
    def test_category_filter_escapes(self):
        assert milvus_client.category_filter(None) == ""
        assert milvus_client.category_filter('退"货') == 'category == "退\\"货"'

    def test_dense_search_converts_hits(self):
        client = FakeMilvus()
        hits = milvus_client.dense_search(client, [0.1], 2, collection="c", category="售后")

        assert hits[0] == {"id": 1, "score": 0.9, "question": "q1", "answer": "a1",
                           "section_path": "p", "content_type": "faq", "category": "c"}
        _, _, kwargs = client.calls[0]
        assert kwargs["anns_field"] == "dense"
        assert kwargs["limit"] == 2
        assert kwargs["filter"] == 'category == "售后"'

    def test_bm25_search(self):
        client = FakeMilvus()
        milvus_client.bm25_search(client, "退货", 3)
        _, _, kwargs = client.calls[0]
        assert (kwargs["anns_field"], kwargs["data"], kwargs["search_params"]) == (
            "sparse", ["退货"], {"metric_type": "BM25"},
        )

    def test_hybrid_search(self):
        client = FakeMilvus()
        assert [h["id"] for h in milvus_client.hybrid_search(client, [0.1], "退货", 5, recall=20)] == [3]
        _, _, kwargs = client.calls[0]
        assert len(kwargs["reqs"]) == 2
        assert kwargs["limit"] == 5

    def test_ensure_existing_collection_validates_schema(self):
        client = FakeMilvus()
        milvus_client.ensure_collection(client, "c")
        assert client.names() == ["has_collection", "describe_collection", "load_collection"]

    @pytest.mark.parametrize(
        "fields,message",
        [
            ([{"name": "dense", "params": {"dim": milvus_client.DIM}}], "字段"),
            ([{"name": "dense", "params": {"dim": 8}}, {"name": "sparse"}, {"name": "text"}], "维度"),
        ],
    )
    def test_ensure_rejects_incompatible_collection(self, fields, message):
        with pytest.raises(ValueError, match=message):
            milvus_client.ensure_collection(FakeMilvus(fields=fields), "c")

    def test_ensure_creates_missing_collection(self):
        client = FakeMilvus(exists=False)
        milvus_client.ensure_collection(client, "new")
        assert "create_collection" in client.names()
        assert client.names()[-1] == "load_collection"

    def test_ensure_cached_for_shared_client(self, monkeypatch):
        client = FakeMilvus()
        monkeypatch.setattr(milvus_client, "_CLIENT", client)
        monkeypatch.setattr(milvus_client, "_ENSURED_COLLECTIONS", set())
        milvus_client.ensure_collection(client, "c")
        milvus_client.ensure_collection(client, "c")
        assert client.names().count("has_collection") == 1

    def test_upsert_flush_count_drop(self):
        client = FakeMilvus()
        milvus_client.upsert_vectors(client, [], collection="c")
        milvus_client.upsert_vectors(client, [{"id": 1}], collection="c")
        milvus_client.flush(client, collection="c")
        assert milvus_client.count(client, "c") == 42
        milvus_client.drop(client, "c")
        assert client.names() == ["upsert", "flush", "query", "has_collection", "drop_collection"]

    async def test_acall_runs_in_executor(self):
        assert await milvus_client.acall(lambda a, b=0: a + b, 1, b=2) == 3


@pytest.fixture
def fake_milvus(monkeypatch):
    client = FakeMilvus()

    async def acall(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(milvus_client, "acall", acall)
    monkeypatch.setattr(milvus_client, "get_client", lambda: client)
    return client


class Row:
    def __init__(self, i):
        self.id = i
        self.category = "c"
        self.questions = f"q{i}"
        self.answer = f"a{i}"
        self.section_path = None
        self.content_type = "faq"


class TestDualwrite:
    async def test_write_pending_delegates(self, monkeypatch):
        ensure = AsyncMock(return_value=[1, 2])
        monkeypatch.setattr(dualwrite.knowledge_repo, "ensure_knowledge_chunks", ensure)
        chunks = [Chunk("c", "q", "a", "p", "faq")]
        assert await dualwrite.write_pending(chunks) == [1, 2]
        ensure.assert_awaited_once_with(chunks)

    async def test_vectorize_in_batches(self, monkeypatch, fake_milvus):
        monkeypatch.setattr(dualwrite.knowledge_repo, "list_pending_chunks", AsyncMock(return_value=[Row(i) for i in range(5)]))
        mark = AsyncMock()
        monkeypatch.setattr(dualwrite.knowledge_repo, "mark_chunk_vectorized", mark)
        embed = AsyncMock(side_effect=lambda texts: [[0.0] * milvus_client.DIM for _ in texts])
        monkeypatch.setattr(dualwrite.embeddings, "embed_texts", embed)

        assert await dualwrite.vectorize_pending(batch_size=2) == 5

        assert [len(c.args[0]) for c in embed.await_args_list] == [2, 2, 1]
        assert embed.await_args_list[0].args[0][0] == "c\nq0\na0"
        upserts = [kwargs["data"] for name, _, kwargs in fake_milvus.calls if name == "upsert"]
        assert [row["id"] for batch in upserts for row in batch] == [0, 1, 2, 3, 4]
        assert upserts[0][0]["section_path"] == ""
        assert [c.args for c in mark.await_args_list] == [(i, str(i)) for i in range(5)]

    @pytest.mark.parametrize(
        "vectors,message",
        [([[0.0] * milvus_client.DIM], "数量"), ([[0.0], [0.0]], "维度")],
    )
    async def test_vectorize_rejects_bad_embeddings(self, monkeypatch, fake_milvus, vectors, message):
        monkeypatch.setattr(dualwrite.knowledge_repo, "list_pending_chunks", AsyncMock(return_value=[Row(1), Row(2)]))
        monkeypatch.setattr(dualwrite.embeddings, "embed_texts", AsyncMock(return_value=vectors))
        with pytest.raises(ValueError, match=message):
            await dualwrite.vectorize_pending()

    async def test_rejects_invalid_batch_size(self):
        with pytest.raises(ValueError):
            await dualwrite.vectorize_pending(batch_size=0)


def verbatim(name):
    text = (KB_DIR / name).read_text(encoding="utf-8")
    return next(line.strip() for line in text.splitlines() if len(line.strip()) > 10 and not line.startswith("#"))[:20]


SOURCE = "returns-policy.md"


class TestMining:
    def test_validate_candidate(self):
        candidate = mining.validate_candidate({"question": "怎么退货", "source_file": SOURCE, "quote": verbatim(SOURCE)})
        assert candidate.source_file == SOURCE

    @pytest.mark.parametrize(
        "item,message",
        [
            ({"question": "q", "source_file": "x.md", "quote": "a"}, "白名单"),
            ({"question": "q", "source_file": SOURCE, "quote": "不存在的原文ZZZ"}, "连续原文"),
            ({"question": "ORD-1 怎么退", "source_file": SOURCE, "quote": verbatim(SOURCE)}, "脱敏"),
        ],
    )
    def test_validate_candidate_rejections(self, item, message):
        with pytest.raises(ValueError, match=message):
            mining.validate_candidate(item)

    def test_stage_candidates_dedupes(self):
        quote = verbatim(SOURCE)
        staged = mining.stage_candidates(
            [{"question": "怎么 退货", "status": "approved"}],
            [
                {"question": "怎么退货", "source_file": SOURCE, "quote": quote},
                {"question": "运费谁出", "source_file": SOURCE, "quote": quote},
                {"question": "运费 谁出", "source_file": SOURCE, "quote": quote},
            ],
        )
        assert [item["question"] for item in staged] == ["怎么 退货", "运费谁出"]
        assert staged[1]["status"] == "pending"

    async def test_mine_dialogue(self, monkeypatch):
        quote = verbatim(SOURCE)
        result = mining.Candidates(items=[
            mining.Candidate(question="怎么退货", source_file=SOURCE, quote=quote),
        ])
        patch_model(monkeypatch, mining, FakeStructuredModel(result))
        staged = await mining.mine_dialogue([{"role": "user", "content": "怎么退货"}])
        assert staged[0]["question"] == "怎么退货"

    async def test_publish_requires_review(self, monkeypatch):
        write = AsyncMock(return_value=[7])
        monkeypatch.setattr(mining, "write_pending", write)
        item = {"question": "怎么退货", "source_file": SOURCE, "quote": verbatim(SOURCE)}

        with pytest.raises(ValueError, match="审核"):
            await mining.publish_approved({**item, "status": "pending", "reviewer": "a"})
        with pytest.raises(ValueError, match="审核"):
            await mining.publish_approved({**item, "status": "approved", "reviewer": " "})

        assert await mining.publish_approved({**item, "status": "approved", "reviewer": "a"}) == [7]
        chunk = write.await_args.args[0][0]
        assert (chunk.category, chunk.content_type) == ("审核问答", SOURCE_TYPES[SOURCE])


REVIEW = {
    "status": "approved",
    "question": "怎么退货",
    "source_ref": SOURCE,
}


class FakeIndex:
    def __init__(self, visible=True):
        self.upserted = []
        self._visible = visible

    async def upsert(self, chunk):
        self.upserted.append(chunk)

    async def visible(self, chunk):
        return self._visible


class TestPublishReview:
    @pytest.fixture
    def repo(self, monkeypatch):
        from app.core.trusted_sources import validate_review_source

        answer = verbatim(SOURCE)
        digest = validate_review_source("怎么退货", answer, SOURCE)
        fake = {
            "get_review_detail": AsyncMock(return_value={**REVIEW, "answer": answer, "source_digest": digest}),
            "prepare_review_chunk": AsyncMock(return_value={"id": 99, "question": "q", "answer": answer}),
            "finish_review_publish": AsyncMock(return_value={"id": 1, "status": "approved"}),
            "note_review_publish_error": AsyncMock(),
        }
        for name, value in fake.items():
            monkeypatch.setattr(review_publish.review_repo, name, value)
        return fake

    async def test_publishes(self, repo):
        index = FakeIndex()
        result = await review_publish.publish_review(1, index=index)
        assert result == {"id": 1, "status": "approved", "chunk_id": 99}
        assert index.upserted[0]["id"] == 99
        repo["prepare_review_chunk"].assert_awaited_once_with(1, SOURCE_TYPES[SOURCE])

    async def test_missing_review(self, repo):
        repo["get_review_detail"].return_value = None
        with pytest.raises(LookupError):
            await review_publish.publish_review(1, index=FakeIndex())

    async def test_unapproved_review(self, repo):
        repo["get_review_detail"].return_value["status"] = "pending"
        with pytest.raises(ValueError, match="核准"):
            await review_publish.publish_review(1, index=FakeIndex())

    async def test_source_changed(self, repo):
        repo["get_review_detail"].return_value["source_digest"] = "old"
        with pytest.raises(ValueError, match="版本"):
            await review_publish.publish_review(1, index=FakeIndex())
        repo["note_review_publish_error"].assert_awaited_once_with(1, "ValueError")

    async def test_not_visible_records_error(self, repo):
        with pytest.raises(RuntimeError):
            await review_publish.publish_review(1, index=FakeIndex(visible=False))
        repo["note_review_publish_error"].assert_awaited_once_with(1, "RuntimeError")
        repo["finish_review_publish"].assert_not_awaited()

    async def test_milvus_index(self, monkeypatch, fake_milvus):
        monkeypatch.setattr(
            review_publish.embeddings, "embed_texts",
            AsyncMock(return_value=[[0.0] * milvus_client.DIM]),
        )
        chunk = {"id": 5, "category": "c", "question": "q", "answer": "a", "section_path": None, "content_type": "faq"}
        index = review_publish.MilvusReviewIndex(collection="c")

        await index.upsert(chunk)
        fake_milvus._query = lambda **kwargs: [{"id": 5, "question": "q", "answer": "a"}]
        assert await index.visible(chunk) is True
        fake_milvus._query = lambda **kwargs: [{"id": 5, "question": "q", "answer": "旧"}]
        assert await index.visible(chunk) is False

        upsert = next(kwargs for name, _, kwargs in fake_milvus.calls if name == "upsert")
        assert upsert["data"][0]["text"] == "c\nq\na"
        assert upsert["data"][0]["section_path"] == ""

    async def test_milvus_index_rejects_bad_vector(self, monkeypatch, fake_milvus):
        monkeypatch.setattr(review_publish.embeddings, "embed_texts", AsyncMock(return_value=[[0.0]]))
        with pytest.raises(ValueError):
            await review_publish.MilvusReviewIndex().upsert(
                {"id": 1, "category": "c", "question": "q", "answer": "a", "section_path": "", "content_type": ""},
            )
