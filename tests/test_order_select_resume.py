"""
测试订单选择的断点恢复和并发处理
覆盖SQLite持久化、选择/取消流程、状态恢复和并发消费
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import make_nodes
from app.graph.runtime import Runtime
from app.graph.state import ConversationState


def setup_runtime(checkpointer=None):
    """构造测试运行时和假服务"""
    order = {"order_id": "ORD-1001", "user_id": "u1", "product_name": "杯子"}
    services = SimpleNamespace(
        max_steps=3,
        list_orders=AsyncMock(return_value=[order]),
        get_order=AsyncMock(return_value=order),
    )
    graph = StateGraph(ConversationState)
    graph.add_node("fetch_order", make_nodes(services)["fetch_order"])
    graph.add_edge(START, "fetch_order")
    graph.add_edge("fetch_order", END)
    return Runtime(graph.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())), services


async def pause(runtime):
    """运行到中断点并返回选择卡片"""
    result = await runtime.run_turn("我要退款", "u1", "resume-test")
    card = result["__interrupt__"][0].value
    return {"kind": "select_order", "request_id": card["request_id"], "order_id": "ORD-1001"}


@pytest.mark.parametrize("cancelled", [False, True])
def test_sqlite_reopen_preserves_pending_card(tmp_path, cancelled):
    """测试SQLite持久化：重开连接后恢复待选卡片，消费后不可重复恢复"""
    async def run():
        path = str(tmp_path / "selection.sqlite")
        async with AsyncSqliteSaver.from_conn_string(path) as saver:
            runtime, _ = setup_runtime(saver)
            choice = await pause(runtime)
        async with AsyncSqliteSaver.from_conn_string(path) as saver:
            runtime, services = setup_runtime(saver)
            pending = await runtime.pending_interrupt("u1", "resume-test")
            assert pending["kind"] == "select_order"
            assert pending["request_id"] == choice["request_id"]
            if cancelled:
                choice.pop("order_id")
                choice["cancelled"] = True
            result = await runtime.run_turn("", "u1", "resume-test", resume=choice)
            assert result["route"] == ("cancelled" if cancelled else "policy")
            assert result["request_id"] == choice["request_id"]
            assert len(result["messages"]) == 1
            assert services.get_order.await_count == (0 if cancelled else 1)
            assert await runtime.pending_interrupt("u1", "resume-test") is None
        async with AsyncSqliteSaver.from_conn_string(path) as saver:
            runtime, _ = setup_runtime(saver)
            with pytest.raises(ValueError, match="没有待恢复"):
                await runtime.run_turn("", "u1", "resume-test", resume=choice)
    asyncio.run(run())


def test_concurrent_selection_is_consumed_once():
    """测试并发选择：同一请求并发消费时只处理一次"""
    async def run():
        runtime, services = setup_runtime()
        choice = await pause(runtime)
        results = await asyncio.gather(
            runtime.run_turn("", "u1", "resume-test", resume=choice),
            runtime.run_turn("", "u1", "resume-test", resume=choice),
            return_exceptions=True,
        )
        completed = [result for result in results if isinstance(result, dict)]
        rejected = [result for result in results if isinstance(result, ValueError)]
        assert len(completed) == len(rejected) == 1
        assert completed[0]["route"] == "policy"
        assert "没有待恢复" in str(rejected[0])
        services.get_order.assert_awaited_once_with("ORD-1001")
    asyncio.run(run())
