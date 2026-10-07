"""
测试知识挖掘模块
验证候选知识的审核门控、去重和引用验证功能
"""
import asyncio
from unittest.mock import AsyncMock
import pytest
from app.kb import mining


def test_review_gate_and_dedup(monkeypatch):
    """测试审核门控和去重：只有approved状态才能发布，相同候选去重，引用需在源文件中存在"""
    name = next(iter(mining.SOURCE_TYPES))
    quote = (mining.KB_DIR / name).read_text(encoding="utf-8").splitlines()[0]
    item = {"question": "通用问题", "quote": quote, "source_file": name}
    staged = mining.stage_candidates([], [item, item])
    assert len(staged) == 1
    write = AsyncMock(return_value=[1])
    monkeypatch.setattr(mining, "write_pending", write)
    with pytest.raises(ValueError):
        asyncio.run(mining.publish_approved(staged[0]))
    write.assert_not_awaited()
    staged[0].update(status="approved", reviewer="teacher")
    assert asyncio.run(mining.publish_approved(staged[0])) == [1]
    with pytest.raises(ValueError):
        mining.validate_candidate({**item, "quote": "不存在的虚构条款"})
