"""app.graph.adapters：真实服务容器的装配、窗口化 agent 消息、工具适配器（LLM 为替身）。"""
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.prompts import CHAT_SYSTEM_PROMPT
from app.graph import adapters
from app.tools.context import ToolContext
from tests.helpers import FakeStructuredModel, patch_model

CTX = ToolContext(user_id="u1", conversation_id="c1")


class TestToolRegistry:
    def test_registers_order_and_ticket_tools(self):
        registry = adapters.make_tool_registry()

        order = registry.get("query_order")
        ticket = registry.get("create_ticket")
        assert (order.permission, order.max_retries) == ("read", 2)
        assert ticket.permission == "write"
        assert order.schema["additionalProperties"] is False
        assert "user_id" not in order.schema["properties"]
        assert {tool["function"]["name"] for tool in registry.model_tools()} == {"query_order", "create_ticket"}

    async def test_order_tool_injects_server_side_user(self):
        assert (await adapters.order_tool({"order_id": "ORD-1001"}, CTX, "c1"))["found"] is True
        other = await adapters.order_tool({"order_id": "ORD-1002"}, CTX, "c1")
        assert other["code"] == "order_not_owned"

    async def test_ticket_tool_previews(self):
        result = await adapters.ticket_tool({"ticket_type": "退款", "description": "坏了"}, CTX, "c1")
        assert result["requires_confirmation"] is True

    async def test_order_helpers(self):
        assert [o["order_id"] for o in await adapters.list_orders("u1")] == ["ORD-1001"]
        assert (await adapters.get_verified_order("ORD-1001"))["user_id"] == "u1"


class TestMakeServices:
    def test_wires_everything(self):
        services = adapters.make_services()
        assert services.registry is not None
        assert set(services.tools) == {"query_order", "create_ticket"}
        assert services.check_sufficient is not None
        assert services.rerank_policy is not None
        assert services.retrieve_detailed is adapters.retrieve_detailed
        # 节点需要的数据飞轮写入、转人工和阈值都由这里装配，节点自己不引用 db / core.handoff / settings
        assert services.save_turn is adapters.flywheel_repo.save_turn
        assert services.capture_low_confidence is adapters.flywheel_repo.capture_low_confidence
        assert services.request_handoff is adapters.handoff.request_from_graph
        assert services.evidence_min_confidence == adapters.settings.evidence_min_confidence

    async def test_with_mcp_reports_issues(self):
        class Transport:
            async def list_tools(self, server):
                raise ConnectionError()

        services, issues = await adapters.make_services_with_mcp(Transport(), ["logistics"])
        assert services.registry.get("query_logistics") is None
        assert issues[0]["code"] == "discovery_failed"

    async def test_with_no_servers(self):
        services, issues = await adapters.make_services_with_mcp(None, [])
        assert issues == []


class TestRetrievalWrappers:
    async def test_use_hybrid_rerank(self, monkeypatch):
        search = AsyncMock(return_value=[{"id": 1}])
        detailed = AsyncMock(return_value={"candidates": [], "evidence": []})
        monkeypatch.setattr(adapters, "search_knowledge", search)
        monkeypatch.setattr(adapters, "search_knowledge_detailed", detailed)

        await adapters.retrieve("q")
        await adapters.retrieve_detailed("q")

        assert search.await_args.kwargs == {"strategy": "hybrid_rerank", "top_k": 5}
        assert detailed.await_args.kwargs == {"strategy": "hybrid_rerank", "top_k": 5}

    async def test_answer_delegates(self, monkeypatch):
        answer = AsyncMock(return_value={"answer": "x"})
        monkeypatch.setattr(adapters, "answer_from_hits", answer)
        await adapters.answer("q", [{"id": 1}], order={"order_id": "ORD-1"}, summary_text="s")
        assert answer.await_args.kwargs == {"order": {"order_id": "ORD-1"}, "summary_text": "s"}


class TestMessageWindow:
    MESSAGES = [
        HumanMessage(content="查订单"),
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "query_order", "args": {}}]),
        ToolMessage(content="{}", tool_call_id="c1"),
        AIMessage(content="已发货"),
        HumanMessage(content="谢谢"),
    ]

    def test_select_keeps_whole_turns(self):
        assert adapters.select_original_window(self.MESSAGES, budget=100_000) == self.MESSAGES

    def test_select_respects_covered_count(self):
        assert adapters.select_original_window(self.MESSAGES, budget=100_000, covered_count=4) == self.MESSAGES[4:]

    def test_select_drops_old_turns_under_tight_budget(self):
        selected = adapters.select_original_window(self.MESSAGES, budget=150)
        assert selected == self.MESSAGES[4:]

    @pytest.mark.parametrize("covered", [-1, 6])
    def test_select_rejects_bad_covered_count(self, covered):
        with pytest.raises(ValueError):
            adapters.select_original_window(self.MESSAGES, 1000, covered_count=covered)

    def test_select_rejects_system_messages(self):
        with pytest.raises(ValueError, match="不支持"):
            adapters.select_original_window([SystemMessage(content="x")], 1000)

    def test_build_agent_messages(self):
        messages = adapters.build_agent_messages([HumanMessage(content="hi")], " 摘要 ")
        assert messages[0].content == CHAT_SYSTEM_PROMPT
        assert json.loads(messages[1].content) == {"type": "untrusted_conversation_summary", "text": "摘要"}
        assert messages[2].content == "hi"
        assert len(adapters.build_agent_messages([], "")) == 1

    def test_windowed_messages(self):
        messages = adapters.build_windowed_agent_messages(self.MESSAGES, covered_count=4)
        assert [m.type for m in messages] == ["system", "human"]


class TestModelBackedServices:
    async def test_agent_binds_tools(self, monkeypatch):
        model = patch_model(monkeypatch, adapters, FakeStructuredModel(parsed=AIMessage(content="ok")))
        result = await adapters.agent([HumanMessage(content="hi")], model_tools=[{"type": "function"}])
        assert result.content == "ok"
        assert model.tools == [{"type": "function"}]
        assert model.calls[0][0].type == "system"

    async def test_classify_detail(self, monkeypatch):
        from app.core.intent import Intent, Prediction

        patch_model(monkeypatch, adapters, FakeStructuredModel(Prediction(intent=Intent.ORDER, confidence=0.9)))
        prediction, route = await adapters.classify_detail("查订单")
        assert (prediction.intent, route) == (Intent.ORDER, "business")

    async def test_legacy_classify(self, monkeypatch):
        patch_model(monkeypatch, adapters, FakeStructuredModel(adapters.Intent(route="chat")))
        assert await adapters.classify("你好") == "chat"

    async def test_expand_policy_caps_at_two(self, monkeypatch):
        patch_model(monkeypatch, adapters, FakeStructuredModel(adapters.PolicyQueries(queries=["a", "b", "c"])))
        assert await adapters.expand_policy("q") == ["a", "b"]

    @pytest.mark.parametrize(
        "model",
        [FakeStructuredModel(parsing_error=ValueError()), FakeStructuredModel(parsed=None),
         FakeStructuredModel(error=RuntimeError())],
    )
    async def test_expand_policy_failures_return_empty(self, monkeypatch, model):
        patch_model(monkeypatch, adapters, model)
        assert await adapters.expand_policy("q") == []
