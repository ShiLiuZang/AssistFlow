"""
测试政策检索的查询扩展和结果合并
覆盖查询去重、命中合并、缺失字段过滤和异常输入拒绝
"""
import asyncio

from app.core.retrieval import retrieve_policy


def test_policy_retrieval_bounds_queries_and_merges_hits():
    """测试政策检索：限制查询数量，去重并合并命中结果"""
    searched = []

    async def expand(_query):
        return [
            "退货政策",
            "退货 ORD-9999",
            "退货政策",
            "第三个扩展",
        ]

    async def search(query):
        searched.append(query)
        return [
            {"id": 1, "answer": "旧答案", "section_path": "售后", "rerank_score": 0.4},
            {"id": 1, "answer": "高分答案", "section_path": "售后", "rerank_score": 0.9},
            {"id": 2, "answer": "低分", "section_path": "售后", "rerank_score": 0.2},
            {"id": 3, "answer": "缺来源", "rerank_score": 0.8},
        ]

    queries, hits = asyncio.run(
        retrieve_policy("ORD-1001 退货", {"order_id": "ORD-1001"}, expand, search)
    )
    assert queries == ["ORD-1001 退货", "退货政策", "第三个扩展"]
    assert searched == queries
    assert [hit["id"] for hit in hits] == [1]
    assert hits[0]["answer"] == "高分答案"
    assert hits[0]["n"] == 1


def test_policy_retrieval_rejects_non_list_expansion():
    """测试扩展结果验证：非列表类型应被拒绝"""
    async def expand(_query):
        return "not a list"

    async def search(_query):
        return []

    try:
        asyncio.run(retrieve_policy("退货", None, expand, search))
    except ValueError as exc:
        assert str(exc) == "扩展结果必须是列表"
    else:
        raise AssertionError("expected ValueError")
