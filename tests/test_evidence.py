"""
第三课证据评估功能的单元测试

测试覆盖:
- compute_evidence_confidence: 置信度计算
- snapshot_from_hits: 证据快照生成
- evidence_gate: 证据门控机制
"""
import pytest
from unittest.mock import AsyncMock
from app.core.confidence import (
    compute_evidence_confidence,
    snapshot_from_hits,
    evidence_gate,
)


class TestComputeEvidenceConfidence:
    """测试置信度计算函数"""

    def test_normal_case(self):
        """正常情况: 多个候选的平均分"""
        hits = [
            {"id": 1, "rerank_score": 0.8, "question": "问题1", "answer": "答案1"},
            {"id": 2, "rerank_score": 0.6, "question": "问题2", "answer": "答案2"},
            {"id": 3, "rerank_score": 0.7, "question": "问题3", "answer": "答案3"},
        ]
        result = compute_evidence_confidence(hits)

        assert "score" in result
        assert "signals" in result
        assert result["signals"]["valid_count"] == 3
        assert result["signals"]["top1_score"] == 0.8

    def test_single_hit(self):
        """单个候选"""
        hits = [{"id": 1, "rerank_score": 0.85, "question": "问题", "answer": "答案"}]
        result = compute_evidence_confidence(hits)

        assert "score" in result
        assert result["signals"]["valid_count"] == 1
        assert result["signals"]["top1_score"] == 0.85

    def test_empty_hits(self):
        """空候选列表"""
        result = compute_evidence_confidence([])

        assert result["score"] == 0.0
        assert result["signals"]["valid_count"] == 0

    def test_missing_rerank_score(self):
        """缺少 rerank_score 字段"""
        hits = [
            {"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"},
            {"id": 2, "question": "Q2", "answer": "A2"},
        ]


        with pytest.raises(ValueError, match="精排分数必须是 0 到 1 之间的有限数值"):
            compute_evidence_confidence(hits)

    def test_extreme_scores(self):
        """极端分数: 0 和 1"""
        hits = [
            {"id": 1, "rerank_score": 0.0, "question": "Q1", "answer": "A1"},
            {"id": 2, "rerank_score": 1.0, "question": "Q2", "answer": "A2"},
        ]
        result = compute_evidence_confidence(hits)

        assert "score" in result
        assert result["signals"]["valid_count"] >= 1
        assert result["signals"]["top1_score"] == 1.0


class TestSnapshotFromHits:
    """测试证据快照生成函数"""

    def test_default_fields(self):
        """使用默认字段"""
        hits = [
            {
                "id": 1,
                "question": "问题1",
                "answer": "答案1",
                "section_path": "退换货/流程",
                "rerank_score": 0.8,
            },
            {
                "id": 2,
                "question": "问题2",
                "answer": "答案2",
                "section_path": "售后/保修",
                "rerank_score": 0.6,
            },
        ]
        snapshot = snapshot_from_hits(hits)

        assert len(snapshot) == 2
        assert snapshot[0]["id"] == 1
        assert snapshot[0]["section_path"] == "退换货/流程"
        assert snapshot[0]["rerank_score"] == 0.8

    def test_custom_fields(self):
        """自定义字段列表 - 已移除不支持的功能"""
        hits = [
            {
                "id": 1,
                "question": "问题1",
                "answer": "详细答案",
                "section_path": "退换货/流程",
                "rerank_score": 0.8,
            }
        ]
        snapshot = snapshot_from_hits(hits)

        assert len(snapshot) == 1
        assert snapshot[0]["id"] == 1
        assert snapshot[0]["answer"] == "详细答案"

    def test_missing_fields(self):
        """候选中缺少某些字段"""
        hits = [
            {"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"},

        ]
        snapshot = snapshot_from_hits(hits)

        assert snapshot[0]["id"] == 1
        assert snapshot[0]["section_path"] is None

    def test_empty_hits(self):
        """空候选列表"""
        snapshot = snapshot_from_hits([])
        assert snapshot == []


class TestEvidenceGate:
    """测试证据门控机制"""

    @pytest.mark.asyncio
    async def test_pass_all_checks(self):
        """通过所有检查: 证据充分"""
        hits = [{"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"}]
        check = AsyncMock(return_value={"useful": True})

        decision = await evidence_gate(
            question="如何退货?",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=hits,
        )

        assert decision.allow is True
        assert decision.source is None
        assert decision.reason == "passed"
        assert "score" in decision.confidence
        assert len(decision.snapshot) <= 3
        check.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_candidates(self):
        """第一层拒绝: 候选列表为空"""
        check = AsyncMock()

        decision = await evidence_gate(
            question="如何退货?",
            hits=[],
            threshold=0.5,
            check=check,
            evidence=[],
        )

        assert decision.allow is False
        assert decision.source == "retrieval_low_conf"
        assert decision.reason == "no_evidence"
        assert decision.confidence["score"] == 0.0
        check.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_eligible_evidence(self):
        """第二层拒绝: 证据列表为空"""
        hits = [{"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"}]
        check = AsyncMock()

        decision = await evidence_gate(
            question="如何退货?",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=[],
        )

        assert decision.allow is False
        assert decision.source == "retrieval_low_conf"
        assert decision.reason == "no_eligible_evidence"
        check.assert_not_called()

    @pytest.mark.asyncio
    async def test_below_threshold(self):
        """第三层拒绝: 置信度低于阈值"""
        hits = [{"id": 1, "rerank_score": 0.3, "question": "Q1", "answer": "A1"}]
        check = AsyncMock()

        decision = await evidence_gate(
            question="如何退货?",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=hits,
        )

        assert decision.allow is False
        assert decision.source == "retrieval_low_conf"
        assert decision.reason == "score_below_threshold"
        assert "score" in decision.confidence
        check.assert_not_called()

    @pytest.mark.asyncio
    async def test_insufficient_evidence_by_llm(self):
        """第四层拒绝: LLM 判断证据不充分"""
        hits = [{"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"}]
        check = AsyncMock(return_value={"useful": False})

        decision = await evidence_gate(
            question="如何退货?",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=hits,
        )

        assert decision.allow is False
        assert decision.source == "self_check"
        assert decision.reason == "insufficient_evidence"
        check.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_error(self):
        """充分性检查异常"""
        hits = [{"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"}]
        check = AsyncMock(side_effect=RuntimeError("LLM 调用失败"))

        decision = await evidence_gate(
            question="如何退货?",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=hits,
        )

        assert decision.allow is False
        assert decision.source == "self_check"
        assert decision.reason == "check_error"

    @pytest.mark.asyncio
    async def test_check_invalid_return(self):
        """充分性检查返回格式错误"""
        hits = [{"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"}]
        check = AsyncMock(return_value={"result": "yes"})

        decision = await evidence_gate(
            question="如何退货?",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=hits,
        )

        assert decision.allow is False
        assert decision.source == "self_check"
        assert decision.reason == "check_error"

    @pytest.mark.asyncio
    async def test_threshold_validation(self):
        """阈值参数验证"""
        hits = [{"id": 1, "rerank_score": 0.8, "question": "Q1", "answer": "A1"}]
        check = AsyncMock()


        invalid_thresholds = [
            -0.1,
            1.5,
            float("inf"),
            float("nan"),
            True,
            "0.5",
        ]

        for invalid in invalid_thresholds:
            with pytest.raises(ValueError, match="证据阈值必须是 0 到 1 之间的有限数值"):
                await evidence_gate(
                    question="test",
                    hits=hits,
                    threshold=invalid,
                    check=check,
                    evidence=hits,
                )

    @pytest.mark.asyncio
    async def test_threshold_boundaries(self):
        """阈值边界测试"""
        hits = [{"id": 1, "rerank_score": 0.9, "question": "Q1", "answer": "A1"}]
        check = AsyncMock(return_value={"useful": True})


        decision = await evidence_gate(
            question="test",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=hits,
        )
        assert decision.allow is True


        low_hits = [{"id": 1, "rerank_score": 0.3, "question": "Q1", "answer": "A1"}]
        decision = await evidence_gate(
            question="test",
            hits=low_hits,
            threshold=0.5,
            check=check,
            evidence=low_hits,
        )
        assert decision.allow is False
        assert decision.reason == "score_below_threshold"

    @pytest.mark.asyncio
    async def test_confidence_and_snapshot_always_present(self):
        """无论通过与否, confidence 和 snapshot 都应该存在"""
        hits = [{"id": 1, "rerank_score": 0.3, "question": "Q1", "answer": "A1"}]
        check = AsyncMock()

        decision = await evidence_gate(
            question="test",
            hits=hits,
            threshold=0.5,
            check=check,
            evidence=hits,
        )

        assert "score" in decision.confidence
        assert "signals" in decision.confidence
        assert isinstance(decision.snapshot, list)


class TestIntegrationScenarios:
    """集成场景测试"""

    @pytest.mark.asyncio
    async def test_typical_workflow(self):
        """典型工作流: 从检索到决策"""

        retrieval_hits = [
            {
                "id": 1,
                "question": "退货流程是什么?",
                "answer": "7 天无理由退货...",
                "section_path": "退换货政策/退货流程",
                "rerank_score": 0.82,
            },
            {
                "id": 2,
                "question": "退货需要什么条件?",
                "answer": "需要保持商品完好...",
                "section_path": "退换货政策/退货条件",
                "rerank_score": 0.75,
            },
        ]


        check = AsyncMock(return_value={"useful": True, "reason": "包含完整流程和条件"})


        decision = await evidence_gate(
            question="我想退货,怎么办理?",
            hits=retrieval_hits,
            threshold=0.6,
            check=check,
            evidence=retrieval_hits,
        )


        assert decision.allow is True
        assert "score" in decision.confidence
        assert len(decision.snapshot) <= 3


        call_args = check.call_args
        assert call_args[0][0] == "我想退货,怎么办理?"
        assert len(call_args[0][1]) >= 1

    @pytest.mark.asyncio
    async def test_edge_case_exact_threshold(self):
        """边界情况: 高置信度通过门控"""
        hits = [
            {"id": 1, "rerank_score": 0.9, "question": "Q1", "answer": "A1"},
            {"id": 2, "rerank_score": 0.8, "question": "Q2", "answer": "A2"},
        ]

        check = AsyncMock(return_value={"useful": True})

        decision = await evidence_gate(
            question="test",
            hits=hits,
            threshold=0.6,
            check=check,
            evidence=hits,
        )

        assert decision.allow is True
