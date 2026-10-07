"""
测试共指消解功能
覆盖实体提取、指代词解析、多候选澄清和已选订单绑定
"""
from types import SimpleNamespace

from app.core.coref import entities, resolve


def human(text):
    """构造人类消息"""
    return SimpleNamespace(type="human", content=text)


def test_entities_normalize_and_deduplicate_ids():
    """测试实体提取：大小写归一化和去重"""
    assert entities("ORD-1001 and ord-1001, MH-ab12") == ["ORD-1001", "MH-AB12"]


def test_complete_query_is_passed_through():
    """测试完整查询：包含实体ID的问题直接通过"""
    result = resolve("ORD-1001 能退吗？", [human("ORD-9999")])
    assert result.original == "ORD-1001 能退吗？"
    assert result.resolved == result.original
    assert result.needs_clarification is False


def test_single_human_candidate_resolves_reference():
    """测试单候选消解：指代词解析到唯一的历史实体"""
    result = resolve("这个能退吗？", [human("查一下 ORD-1001")])
    assert result.original == "这个能退吗？"
    assert result.resolved == "ORD-1001能退吗？"
    assert result.needs_clarification is False


def test_assistant_entity_is_not_trusted():
    """测试助手消息过滤：不信任AI消息中的实体"""
    result = resolve(
        "这个能退吗？",
        [SimpleNamespace(type="ai", content="我来看看 ORD-9999")],
    )
    assert result.resolved == result.original
    assert result.needs_clarification is True


def test_multiple_human_candidates_require_clarification():
    """测试多候选澄清：多个历史实体时需要用户明确"""
    result = resolve(
        "那个订单能退吗？",
        [human("ORD-1001 怎么查物流"), human("ORD-1002 已签收")],
    )
    assert result.resolved == result.original
    assert result.needs_clarification is True


def test_verified_selected_order_can_resolve_reference():
    """测试已选订单绑定：用户选中的订单可用于消解"""
    result = resolve("它能退吗？", [], selected_order="ORD-1001")
    assert result.resolved == "ORD-1001能退吗？"
