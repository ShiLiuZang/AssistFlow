"""完整对话图：用真实 build_graph + 内存检查点跑各条分支，服务容器为替身。"""
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.handoff import queue_reply
from app.graph import nodes
from app.graph.routing import confidence_gate, route_by_intent, should_continue
from tests.graph.conftest import (
    ANSWER,
    GOOD_HIT,
    ORDER,
    make_registry,
    make_services,
    runtime_for,
    scripted_agent,
    tool_call,
)


class TestRouting:
    @pytest.mark.parametrize("route", ["knowledge", "business", "refund", "complaint", "human", "chat", "clarify"])
    def test_known_routes(self, route):
        assert route_by_intent({"route": route}) == route

    @pytest.mark.parametrize("state", [{}, {"route": "policy"}, {"route": None}])
    def test_unknown_route_clarifies(self, state):
        assert route_by_intent(state) == "clarify"

    @pytest.mark.parametrize(
        "state,expected",
        [
            ({"evidence_allowed": True, "evidence": [{"id": 1}]}, "answer"),
            ({"evidence_allowed": True, "evidence": []}, "fallback"),
            ({"evidence_allowed": 1, "evidence": [{"id": 1}]}, "fallback"),
            ({"evidence": [{"id": 1}]}, "fallback"),
        ],
    )
    def test_confidence_gate(self, state, expected):
        assert confidence_gate(state) == expected

    def test_should_continue(self):
        calling = AIMessage(content="", tool_calls=[tool_call("c1", "query_order", {})])
        assert should_continue({"messages": [calling]}) == "tools"
        assert should_continue({"messages": [AIMessage(content="完成")]}) == "finish"
        assert should_continue({"messages": []}) == "finish"


def test_make_nodes_rejects_invalid_max_steps():
    with pytest.raises(ValueError):
        nodes.make_nodes(make_services(max_steps=0))


TRACE_PREFIX = ["resolve_reference", "classify"]


class TestKnowledgeBranch:
    async def test_answer_with_citations(self, repo):
        services = make_services()
        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")

        assert result["trace"] == TRACE_PREFIX + ["retrieve", "answer", "finish"]
        assert result["answer"] == ANSWER
        assert result["citations"][0]["n"] == 1
        assert result["evidence_allowed"] is True
        assert result["intent"] == "knowledge"
        assert result["message_id"] == f"msg_c1_{result['request_id']}"
        assert [m.type for m in result["messages"]] == ["human", "ai"]
        assert result["messages"][-1].content == ANSWER
        saved = repo.save_turn.await_args.kwargs
        assert (saved["owner"], saved["conversation"], saved["question"]) == ("u1", "c1", "退货期限是多久")
        assert saved["snapshot"][0]["id"] == GOOD_HIT["id"]
        repo.capture_low_confidence.assert_not_awaited()

    async def test_low_confidence_falls_back(self, repo):
        weak = {**GOOD_HIT, "rerank_score": 0.31, "question": "q", "answer": "a"}

        async def retrieve(query):
            return {"candidates": [weak], "evidence": [weak]}

        services = make_services(retrieve_detailed=retrieve)
        result = await runtime_for(services).run_turn("问题", "u1", "c1")

        assert result["trace"][-2:] == ["fallback", "finish"]
        assert result["answer"] == nodes.REFUSAL
        assert result["fallback_reason"] == "score_below_threshold"
        services.check_sufficient.assert_not_awaited()
        assert repo.capture_low_confidence.await_args.kwargs["source"] == "retrieval_low_conf"

    async def test_insufficient_evidence_falls_back(self, repo):
        services = make_services(check_sufficient=AsyncMock(return_value={"useful": False}))
        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")

        assert result["answer"] == nodes.REFUSAL
        assert result["evidence"] == []
        assert repo.capture_low_confidence.await_args.kwargs["reason"] == "insufficient_evidence"

    async def test_check_error_has_retry_message(self, repo):
        services = make_services(check_sufficient=AsyncMock(side_effect=TimeoutError()))
        result = await runtime_for(services).run_turn("退货期限是多久", "u1", "c1")
        assert result["answer"].startswith("暂时无法完成资料核对")

    async def test_snapshot_failures_do_not_break_reply(self, repo):
        repo.save_turn.side_effect = RuntimeError("db down")
        result = await runtime_for(make_services()).run_turn("退货期限是多久", "u1", "c1")
        assert result["answer"] == ANSWER
        assert result["message_id"] is None
        repo.capture_low_confidence.assert_not_awaited()

    @pytest.mark.parametrize(
        "reason,source",
        [("no_evidence", "retrieval_low_conf"), ("grounding_failed", "self_check"), ("unsupported_answer", "self_check")],
    )
    async def test_refused_answer_logged(self, repo, reason, source):
        async def refuse(query, evidence, *, order, summary_text):
            return {"answer": "x", "refused": True, "citations": [], "reason": reason}

        result = await runtime_for(make_services(answer=refuse)).run_turn("退货期限", "u1", "c1")

        assert (result["answer"], result["citations"]) == (nodes.REFUSAL, [])
        assert repo.capture_low_confidence.await_args.kwargs == {
            "owner": "u1", "conversation": "c1", "message_id": result["message_id"],
            "source": source, "reason": reason,
        }

    @pytest.mark.parametrize(
        "bad",
        [
            "not a dict",
            {"answer": "x", "reason": None},
            {"answer": "x", "refused": True},
            {"answer": "x", "refused": True, "reason": "made_up"},
            {"answer": "x", "refused": False, "reason": "no_evidence"},
        ],
    )
    async def test_invalid_answer_service_output_raises(self, repo, bad):
        async def answer(query, evidence, *, order, summary_text):
            return bad

        with pytest.raises((ValueError, TypeError)):
            await runtime_for(make_services(answer=answer)).run_turn("退货期限", "u1", "c1")

    async def test_missing_services_raise(self, repo):
        with pytest.raises(ValueError, match="检索服务"):
            await runtime_for(make_services(retrieve_detailed=None)).run_turn("退货", "u1", "c1")
        with pytest.raises(ValueError, match="充分性"):
            await runtime_for(make_services(check_sufficient=None)).run_turn("退货", "u1", "c2")


@pytest.mark.parametrize(
    "route,node,answer_prefix",
    [
        ("chat", "chat", "你好"),
        ("complaint", "complaint", "已了解你的投诉"),
        ("human", "human", "如需人工协助"),
        ("clarify", "clarify_intent", "请补充"),
    ],
)
async def test_canned_branches(repo, route, node, answer_prefix):
    result = await runtime_for(make_services(route=route)).run_turn("随便聊聊", "u1", "c1")
    assert result["trace"] == TRACE_PREFIX + [node, "finish"]
    assert result["answer"].startswith(answer_prefix)


class TestReferenceResolution:
    async def test_ambiguous_reference_asks_first(self, repo):
        services = make_services()
        result = await runtime_for(services).run_turn("那个订单能退吗", "u1", "c1")
        assert result["trace"] == ["resolve_reference", "clarify_reference", "finish"]
        assert services.classify_calls == []

    async def test_reference_resolved_from_history(self, repo):
        services = make_services()
        runtime = runtime_for(services)
        await runtime.run_turn("ORD-7 的退货政策", "u1", "c1")

        result = await runtime.run_turn("那个订单能退吗", "u1", "c1")

        assert result["query"] == "那个订单能退吗"
        assert result["resolved_query"] == "ORD-7能退吗"
        assert services.classify_calls[-1]["query"] == "ORD-7能退吗"

    async def test_recent_context_passed_to_classifier(self, repo):
        services = make_services(route="chat")
        runtime = runtime_for(services)
        await runtime.run_turn("第一句", "u1", "c1")
        await runtime.run_turn("第二句", "u1", "c1")

        context = services.classify_calls[-1]["recent_context"]
        assert [item["role"] for item in context] == ["human", "ai"]
        assert context[0]["content"] == "第一句"


class TestRefundBranch:
    async def test_explicit_order_goes_to_policy(self, repo):
        services = make_services(route="refund", get_order=AsyncMock(return_value=ORDER))
        result = await runtime_for(services).run_turn("ORD-1 能退吗", "u1", "c1")

        assert result["trace"] == TRACE_PREFIX + ["fetch_order", "policy", "answer", "finish"]
        assert (result["order"], result["last_order_id"]) == (ORDER, "ORD-1")
        assert services.answer_calls[0]["order"] == ORDER
        assert services.rerank_policy.await_args.args[0] == "ORD-1 能退吗"

    async def test_policy_uses_expand_service(self, repo):
        services = make_services(route="refund", get_order=AsyncMock(return_value=ORDER))
        services.expand_policy = AsyncMock(return_value=["ORD-1 退货规则"])
        result = await runtime_for(services).run_turn("ORD-1 能退吗", "u1", "c1")
        assert result["queries"] == ["ORD-1 能退吗", "ORD-1 退货规则"]

    async def test_policy_requires_rerank_service(self, repo):
        services = make_services(route="refund", get_order=AsyncMock(return_value=ORDER), rerank_policy=None)
        with pytest.raises(ValueError, match="精排"):
            await runtime_for(services).run_turn("ORD-1 能退吗", "u1", "c1")

    @pytest.mark.parametrize(
        "order,query,answer",
        [
            ({**ORDER, "user_id": "someone"}, "ORD-1 能退吗", "没有找到属于你的这笔订单，请核对订单号。"),
            (None, "ORD-1 能退吗", "没有找到属于你的这笔订单，请核对订单号。"),
            (ORDER, "ORD-1 和 ORD-2 能退吗", "请一次只提供一个订单号。"),
        ],
    )
    async def test_order_problems(self, repo, order, query, answer):
        services = make_services(route="refund", get_order=AsyncMock(return_value=order))
        result = await runtime_for(services).run_turn(query, "u1", "c1")
        assert result["trace"][-2:] == ["order_result", "finish"]
        assert result["answer"] == answer

    async def test_no_orders(self, repo):
        result = await runtime_for(make_services(route="refund")).run_turn("我要退款", "u1", "c1")
        assert result["answer"] == "没有查到你当前可选择的订单。"

    async def test_select_order_interrupt_then_resume(self, repo):
        services = make_services(
            route="refund", list_orders=AsyncMock(return_value=[ORDER]), get_order=AsyncMock(return_value=ORDER),
        )
        runtime = runtime_for(services)

        first = await runtime.run_turn("我要退款", "u1", "c1")
        preview = first["__interrupt__"][0].value
        assert preview == {
            "kind": "select_order",
            "request_id": first["request_id"],
            "orders": [{"order_id": "ORD-1", "product_name": "耳机"}],
        }

        result = await runtime.run_turn(
            "", "u1", "c1",
            resume={"kind": "select_order", "request_id": preview["request_id"], "order_id": "ORD-1"},
        )
        assert result["trace"][-3:] == ["policy", "answer", "finish"]
        services.get_order.assert_awaited_once_with("ORD-1")

    async def test_cancel_selection(self, repo):
        services = make_services(route="refund", list_orders=AsyncMock(return_value=[ORDER]))
        runtime = runtime_for(services)
        first = await runtime.run_turn("我要退款", "u1", "c1")

        result = await runtime.run_turn(
            "", "u1", "c1",
            resume={"kind": "select_order", "request_id": first["request_id"], "cancelled": True},
        )
        assert result["answer"] == "已取消选择订单，本次没有继续处理。"
        services.get_order.assert_not_awaited()


class TestAgentBranch:
    async def test_plain_reply(self, repo):
        services = make_services(route="business", agent=scripted_agent(AIMessage(content="请提供订单号")))
        result = await runtime_for(services).run_turn("帮我查物流", "u1", "c1")

        assert result["trace"] == TRACE_PREFIX + ["agent", "finish"]
        assert [m.content for m in result["messages"]] == ["帮我查物流", "请提供订单号"]

    async def test_read_tool_loop(self, repo):
        order = {"found": True, "order_id": "ORD-1", "status": "已发货"}
        query_order = AsyncMock(return_value=order)
        agent = scripted_agent(
            AIMessage(content="", tool_calls=[tool_call("c1", "query_order", {"order_id": "ORD-1"})]),
            AIMessage(content="订单已发货"),
        )
        services = make_services(route="business", agent=agent, registry=make_registry(query_order=query_order))

        result = await runtime_for(services).run_turn("ORD-1 到哪了", "u1", "c1")

        assert result["trace"] == TRACE_PREFIX + ["agent", "tools", "agent", "finish"]
        assert (result["answer"], result["last_order_id"]) == ("订单已发货", "ORD-1")
        args, context, call_id = query_order.await_args.args
        assert (args, context.user_id, context.conversation_id, call_id) == ({"order_id": "ORD-1"}, "u1", "c1", "c1")
        tool_message = agent.seen[1][-1]
        assert (tool_message.type, tool_message.status, tool_message.name) == ("tool", "success", "query_order")

    async def test_invalid_args_become_error_tool_message(self, repo):
        query_order = AsyncMock()
        agent = scripted_agent(
            AIMessage(content="", tool_calls=[tool_call("c1", "query_order", {"bad": 1})]),
            AIMessage(content="参数有误"),
        )
        services = make_services(route="business", agent=agent, registry=make_registry(query_order=query_order))

        await runtime_for(services).run_turn("查订单", "u1", "c1")

        query_order.assert_not_awaited()
        assert agent.seen[1][-1].status == "error"

    async def test_step_limit(self, repo):
        calls = [AIMessage(content="", tool_calls=[tool_call(f"c{i}", "query_order", {"order_id": "ORD-1"})]) for i in range(2)]
        services = make_services(route="business", max_steps=2, agent=scripted_agent(*calls))

        result = await runtime_for(services).run_turn("查订单", "u1", "c1")

        assert result["trace"].count("agent") == 3
        assert result["answer"] == "工具调用已达上限，请补充信息或联系人工客服。"

    @pytest.mark.parametrize(
        "message",
        [
            AIMessage(content="", tool_calls=[tool_call("c1", "x", {}), tool_call("c1", "y", {})]),
            AIMessage(content="", invalid_tool_calls=[{"id": "c1", "name": "x", "args": "{", "error": "bad", "type": "invalid_tool_call"}]),
        ],
    )
    async def test_malformed_tool_calls_rejected(self, repo, message):
        services = make_services(route="business", agent=scripted_agent(message))
        result = await runtime_for(services).run_turn("查订单", "u1", "c1")
        assert result["answer"] == "工具调用格式错误，请稍后重试。"

    async def test_agent_must_return_ai_message(self, repo):
        async def agent(messages, *, summary_text, covered_count):
            return HumanMessage(content="x")

        with pytest.raises(TypeError):
            await runtime_for(make_services(route="business", agent=agent)).run_turn("查订单", "u1", "c1")

    @pytest.mark.parametrize(
        "confirmed,expected",
        [(True, "工单已创建，工单号：T-1"), (False, "已取消，本次没有创建工单。")],
    )
    async def test_ticket_requires_confirmation(self, repo, confirmed, expected):
        create_ticket = AsyncMock()
        agent = scripted_agent(
            AIMessage(content="", tool_calls=[tool_call("c1", "create_ticket", {"reason": "坏了"})]),
            AIMessage(content="模型总结"),
        )
        audits = []

        async def audit_sink(record):
            audits.append(record)

        services = make_services(
            route="business", agent=agent, registry=make_registry(create_ticket=create_ticket), audit_sink=audit_sink,
        )
        runtime = runtime_for(services)

        first = await runtime.run_turn("我要报修", "u1", "c1")
        assert first["__interrupt__"][0].value == {
            "kind": "confirm_ticket", "tool_call_id": "c1", "preview": {"reason": "坏了"},
        }

        result = await runtime.run_turn(
            "", "u1", "c1",
            resume={"tool_call_id": "c1", "tool_result": {"confirmed": confirmed, "ticket_no": "T-1"}},
        )

        assert result["answer"] == expected
        create_ticket.assert_not_awaited()
        assert audits == []  # 服务端确认已记审计，图内不重复记录

    async def test_mismatched_ticket_decision_denied_and_audited(self, repo):
        agent = scripted_agent(
            AIMessage(content="", tool_calls=[tool_call("c1", "create_ticket", {"reason": "坏了"})]),
            AIMessage(content="未能创建"),
        )
        audits = []

        async def audit_sink(record):
            audits.append(record)

        services = make_services(route="business", agent=agent, audit_sink=audit_sink)
        runtime = runtime_for(services)
        await runtime.run_turn("我要报修", "u1", "c1")

        await runtime.run_turn("", "u1", "c1", resume={"tool_call_id": "other", "tool_result": {"confirmed": True}})

        assert agent.seen[1][-1].status == "error"
        assert audits[0].status == "permission_denied"
        assert audits[0].audit_key == "ticket-node:c1:c1:permission_denied"

    async def test_ticket_with_invalid_args_skips_confirmation(self, repo):
        agent = scripted_agent(
            AIMessage(content="", tool_calls=[tool_call("c1", "create_ticket", {})]),
            AIMessage(content="缺少原因"),
        )
        result = await runtime_for(make_services(route="business", agent=agent)).run_turn("报修", "u1", "c1")
        assert "__interrupt__" not in result
        assert agent.seen[1][-1].status == "error"

    async def test_tools_require_registry(self, repo):
        agent = scripted_agent(AIMessage(content="", tool_calls=[tool_call("c1", "query_order", {"order_id": "1"})]))
        with pytest.raises(RuntimeError, match="注册表"):
            await runtime_for(make_services(route="business", agent=agent, registry=None)).run_turn("q", "u1", "c1")


class TestOutputGuard:
    async def test_agent_promise_is_replaced_in_state_and_messages(self, repo):
        services = make_services(route="business", agent=scripted_agent(AIMessage(content="已为您退款，请注意查收")))
        result = await runtime_for(services).run_turn("给我退钱", "u1", "c1")

        assert result["answer"] == nodes.SAFE_REPLY
        assert [m.content for m in result["messages"]] == ["给我退钱", nodes.SAFE_REPLY]
        assert result["trace"][-2:] == ["output_guard", "finish"]

    async def test_knowledge_promise_is_replaced(self, repo):
        services = make_services()

        async def promising_answer(query, evidence, *, order, summary_text):
            return {"answer": "我们保证全额退款[1]", "refused": False, "citations": [{**evidence[0], "n": 1}], "reason": None}

        services.answer = promising_answer
        result = await runtime_for(services).run_turn("能退吗", "u1", "c1")

        assert result["messages"][-1].content == nodes.SAFE_REPLY

    async def test_policy_explanation_passes(self, repo):
        result = await runtime_for(make_services()).run_turn("退货期限是多久", "u1", "c1")
        assert result["answer"] == ANSWER and "output_guard" not in result["trace"]


class TestHandoffNodes:
    """human / complaint 节点把会话转入人工排队。"""

    @pytest.mark.parametrize("route,reason", [("human", "human"), ("complaint", "complaint")])
    async def test_queues_handoff_with_state(self, repo, route, reason):
        calls = []

        async def request_handoff(state, why, lead):
            calls.append((state, why))
            return queue_reply({"status": "queued", "position": 3}, lead)

        services = make_services(route=route, request_handoff=request_handoff)
        result = await runtime_for(services).run_turn("我要找人工", "u1", "7")

        assert calls[0][1] == reason
        assert calls[0][0]["conversation_id"] == "7" and calls[0][0]["user_id"] == "u1"
        assert "已为您转接人工客服，前面还有 2 位顾客" in result["answer"]

    async def test_first_in_queue(self, repo):
        async def request_handoff(state, why, lead):
            return queue_reply({"status": "queued", "position": 1}, lead)

        result = await runtime_for(make_services(route="human", request_handoff=request_handoff)).run_turn("转人工", "u1", "7")
        assert "您是下一位" in result["answer"]

    async def test_already_with_agent(self, repo):
        async def request_handoff(state, why, lead):
            return queue_reply({"status": "active", "position": None}, lead)

        result = await runtime_for(make_services(route="human", request_handoff=request_handoff)).run_turn("转人工", "u1", "7")
        assert "人工客服正在为您服务" in result["answer"]

    async def test_falls_back_when_handoff_fails(self, repo):
        async def request_handoff(state, why, lead):
            raise RuntimeError("db down")

        result = await runtime_for(make_services(route="complaint", request_handoff=request_handoff)).run_turn("投诉", "u1", "7")
        assert result["answer"].startswith("已了解你的投诉")
