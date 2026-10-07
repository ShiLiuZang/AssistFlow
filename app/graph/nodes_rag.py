"""检索、证据评估和作答节点。"""

from app.config import settings
from app.core.confidence import evidence_gate
from app.core.observability import span
from app.core.retrieval import retrieve_policy_detailed
from app.db import flywheel_repo
from app.graph.state import ConversationState

# 置信度不足时的拒答模板
REFUSAL = "现有知识库没有足够证据确认这个问题，请联系人工客服。"


async def _save_turn_and_capture_low_confidence(
    state: ConversationState,
    query: str,
    message_id: str,
    snapshot,
    *,
    source,
    reason,
    capture,
) -> bool:
    """保存轮次快照，并按调用方条件记录低置信度问题。"""
    turn_saved = False

    try:
        await flywheel_repo.save_turn(
            owner=state["user_id"],
            conversation=str(state["conversation_id"]),
            message_id=message_id,
            turn_id=state["request_id"],
            question=query,
            snapshot=snapshot,
        )
        turn_saved = True
    except Exception:
        # 快照保存失败不影响主流程（静默失败）
        pass

    if capture and turn_saved:
        try:
            await flywheel_repo.capture_low_confidence(
                owner=state["user_id"],
                conversation=str(state["conversation_id"]),
                message_id=message_id,
                source=source,
                reason=reason,
            )
        except Exception:
            # 记录失败不影响主流程
            pass

    return turn_saved


def make_rag_nodes(services, update, trace_sink) -> dict:
    """创建检索与作答节点，共享状态更新和追踪回调。"""
    async def assess_evidence(query: str, result: dict) -> dict:
        """
        评估检索证据的置信度

        调用证据充分性检查服务，判断检索结果是否足够回答问题。

        Args:
            query: 用户查询
            result: 详细检索结果，包含 candidates 和 evidence

        Returns:
            包含以下字段的字典：
            - evidence: 最终证据列表（置信度不足时为空）
            - evidence_confidence: 置信度得分
            - confidence_signals: 置信度信号详情
            - retrieved_snapshot: 检索结果快照
            - evidence_allowed: 是否允许使用证据
            - fallback_source: 降级来源
            - fallback_reason: 降级原因

        Raises:
            ValueError: 如果输入格式不正确或服务未配置
        """
        if not isinstance(result, dict):
            raise ValueError("详细检索结果必须是字典")

        candidates = result.get("candidates")
        evidence = result.get("evidence")

        if not isinstance(candidates, list):
            raise ValueError("证据检查需要精排候选列表")

        if not isinstance(evidence, list):
            raise ValueError("回答证据必须是列表")

        check = getattr(services, "check_sufficient", None)
        if not callable(check):
            raise ValueError("未配置证据充分性检查服务")

        # 使用 span 记录执行追踪
        async with span("evidence_check", trace_sink):
            decision = await evidence_gate(
                query,
                candidates,
                settings.evidence_min_confidence,
                check,
                evidence=evidence,
            )

        return {
            "evidence": evidence if decision.allow else [],
            "evidence_confidence": decision.confidence["score"],
            "confidence_signals": decision.confidence["signals"],
            "retrieved_snapshot": decision.snapshot,
            "evidence_allowed": decision.allow,
            "fallback_source": decision.source,
            "fallback_reason": (
                decision.reason if not decision.allow else None
            ),
        }


    async def retrieve(state: ConversationState):
        """
        知识库检索节点

        从知识库检索相关文档，并评估证据置信度。

        流程：
        1. 获取查询（优先使用消解后的查询）
        2. 调用详细检索服务（召回 + 重排序）
        3. 评估证据置信度
        4. 更新状态

        Args:
            state: 对话状态

        Returns:
            状态更新字典

        Raises:
            ValueError: 如果检索服务未配置
        """
        # 优先使用指代消解后的查询
        query = state.get("resolved_query") or state["query"]

        retrieve_detailed = getattr(
            services,
            "retrieve_detailed",
            None,
        )
        if not callable(retrieve_detailed):
            raise ValueError("未配置详细检索服务")

        # 执行检索并记录 span
        async with span("retrieve", trace_sink):
            result = await retrieve_detailed(query)

        # 评估证据置信度
        values = await assess_evidence(query, result)

        return update(
            state,
            "retrieve",
            **values,
        )


    async def answer(state: ConversationState):
        """
        答案生成节点

        基于检索证据生成答案，并记录回答快照和低置信度问题。

        流程：
        1. 调用答案生成服务（LLM + RAG）
        2. 检查是否拒答（证据不足或自检失败）
        3. 保存回答快照到 Turn 表
        4. 如果拒答，记录到低置信度问题池

        Args:
            state: 对话状态

        Returns:
            状态更新字典，包含 answer 和 citations
        """
        query = state.get("resolved_query") or state["query"]
        evidence = state["evidence"]

        # 调用答案生成服务
        async with span("answer", trace_sink):
            result = await services.answer(
                query,
                evidence,
                order=state.get("order"),  # 订单上下文（如有）
                summary_text=state.get("summary_text", ""),  # 对话摘要
            )

            # 校验返回结果格式
            if not isinstance(result, dict):
                raise ValueError("回答服务必须返回字典")

            refused = result.get("refused")
            if not isinstance(refused, bool):
                raise ValueError("回答服务必须返回布尔值 refused")

            if "reason" not in result:
                raise ValueError("回答服务缺少 reason 字段")

            reason = result["reason"]

            # 如果拒答，校验拒答原因
            if refused:
                allowed_reasons = {
                    "no_evidence",  # 证据不足
                    "unsupported_answer",  # 生成的答案不受证据支持
                    "grounding_failed",  # 基础验证失败
                }
                if (
                        not isinstance(reason, str)
                        or reason not in allowed_reasons
                ):
                    raise ValueError("回答服务返回了无效的拒答原因")

                # 确定降级来源
                source = (
                    "retrieval_low_conf"  # 检索置信度低
                    if reason == "no_evidence"
                    else "self_check"  # 自检失败
                )
            else:
                # 正常回答时 reason 必须为 None
                if reason is not None:
                    raise ValueError("正常回答的 reason 必须为 None")

                source = None

            # 构建消息 ID（用于关联 Turn 快照）
            message_id = f"msg_{state['conversation_id']}_{state['request_id']}"
            snapshot = state.get("retrieved_snapshot")
            # 保存回答快照到 Turn 表
            # 如果拒答且快照已保存，记录到低置信度问题池
            turn_saved = await _save_turn_and_capture_low_confidence(
                state, query, message_id, snapshot,
                source=source, reason=reason, capture=refused and source,
            )

            return update(
                state,
                "answer",
                answer=REFUSAL if refused else result["answer"],  # 拒答时使用模板
                citations=[] if refused else result["citations"],  # 拒答时无引用
                fallback_source=source,
                fallback_reason=reason,
                message_id=message_id if turn_saved else None,
            )


    async def fallback(state: ConversationState):
        """
        降级处理节点

        当检索置信度不足时，返回拒答模板并记录低置信度问题。

        流程：
        1. 确定降级原因（检索低置信度或自检错误）
        2. 保存回答快照
        3. 记录到低置信度问题池

        Args:
            state: 对话状态

        Returns:
            状态更新字典
        """
        # 确定降级原因和答案
        if state.get("fallback_reason") == "check_error":
            answer = "暂时无法完成资料核对，请稍后重试或联系人工客服。"
            source = "self_check"
            reason = "check_error"
        else:
            answer = REFUSAL
            source = state.get("fallback_source", "retrieval_low_conf")
            reason = state.get("fallback_reason", "unknown")

        query = state.get("resolved_query") or state["query"]
        message_id = f"msg_{state['conversation_id']}_{state['request_id']}"
        snapshot = state.get("retrieved_snapshot")
        # 保存回答快照
        # 记录到低置信度问题池
        turn_saved = await _save_turn_and_capture_low_confidence(
            state, query, message_id, snapshot,
            source=source, reason=reason, capture=True,
        )

        return update(
            state,
            "fallback",
            answer=answer,
            citations=[],
            message_id=message_id if turn_saved else None,
        )


    async def policy(state: ConversationState):
        query = state.get("resolved_query") or state["query"]

        expand = getattr(services, "expand_policy", None)
        if expand is None:
            async def expand(_query):
                return []

        search = getattr(services, "retrieve_detailed", None)
        rerank_all = getattr(services, "rerank_policy", None)

        if not callable(search):
            raise ValueError("未配置详细检索服务")

        if not callable(rerank_all):
            raise ValueError("未配置政策统一精排服务")

        async with span("policy_retrieve", trace_sink):
            queries, result = await retrieve_policy_detailed(
                query,
                state.get("order"),
                expand,
                search,
                rerank_all,
            )

        values = await assess_evidence(query, result)

        return update(
            state,
            "policy",
            queries=queries,
            citations=[],
            **values,
        )


    return {
        "retrieve": retrieve,
        "answer": answer,
        "fallback": fallback,
        "policy": policy,
    }
