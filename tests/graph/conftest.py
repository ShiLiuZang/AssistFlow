"""对话图测试的共用替身：服务容器、工具注册表、MySQL 写入。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.build import build_graph
from app.graph.runtime import Runtime
from app.tools.registry import Registry, ToolSpec

GOOD_HIT = {
    "id": 1,
    "question": "退货期限",
    "answer": "签收后7天内可无理由退货。",
    "section_path": "售后/退货",
    "rerank_score": 0.9,
}
ANSWER = "签收后7天内可以退货[1]"
ORDER = {"order_id": "ORD-1", "user_id": "u1", "product_name": "耳机"}


def prediction(intent="商品咨询", confidence=0.9):
    return SimpleNamespace(intent=SimpleNamespace(value=intent), confidence=confidence)


def tool_call(call_id, name, args):
    return {"id": call_id, "name": name, "args": args, "type": "tool_call"}


def make_registry(query_order=None, create_ticket=None):
    registry = Registry()
    registry.register(ToolSpec(
        name="query_order",
        invoke=query_order or AsyncMock(return_value={"found": False}),
        description="查询订单",
        schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    ))
    registry.register(ToolSpec(
        name="create_ticket",
        invoke=create_ticket or AsyncMock(),
        description="创建售后工单",
        schema={
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
            "additionalProperties": False,
        },
        permission="write",
    ))
    return registry


def scripted_agent(*replies):
    """按顺序返回预设的 AIMessage，并记录每次看到的消息列表。"""
    seen = []
    queue = list(replies)

    async def agent(messages, *, summary_text, covered_count):
        seen.append(list(messages))
        return queue.pop(0)

    agent.seen = seen
    return agent


def make_services(route="knowledge", **overrides):
    classify_calls = []

    async def classify(query, *, summary_text, recent_context):
        classify_calls.append({"query": query, "summary_text": summary_text, "recent_context": recent_context})
        return prediction(), route

    async def retrieve_detailed(query):
        return {"candidates": [GOOD_HIT], "evidence": [GOOD_HIT]}

    answer_calls = []

    async def answer(query, evidence, *, order, summary_text):
        answer_calls.append({"query": query, "order": order, "summary_text": summary_text})
        return {"answer": ANSWER, "refused": False, "citations": [{**evidence[0], "n": 1}], "reason": None}

    services = SimpleNamespace(
        max_steps=4,
        classify=classify,
        classify_calls=classify_calls,
        retrieve_detailed=retrieve_detailed,
        check_sufficient=AsyncMock(return_value={"useful": True}),
        answer=answer,
        answer_calls=answer_calls,
        list_orders=AsyncMock(return_value=[]),
        get_order=AsyncMock(return_value=None),
        rerank_policy=AsyncMock(return_value=[GOOD_HIT]),
        registry=make_registry(),
        agent=scripted_agent(AIMessage(content="好的")),
        save_turn=lambda **kwargs: STORE.save_turn(**kwargs),
        capture_low_confidence=lambda **kwargs: STORE.capture_low_confidence(**kwargs),
        evidence_min_confidence=0.5,
    )
    for key, value in overrides.items():
        setattr(services, key, value)
    return services


def runtime_for(services, checkpointer=None):
    return Runtime(build_graph(services, checkpointer=checkpointer or InMemorySaver()))


# make_services 注入的数据飞轮写入（回答快照与低置信度问题池），每个测试由 repo 夹具换成新的替身
STORE = SimpleNamespace(save_turn=AsyncMock(), capture_low_confidence=AsyncMock())


@pytest.fixture
def repo():
    """记录节点通过 services 写入的回答快照与低置信度问题。"""
    STORE.save_turn, STORE.capture_low_confidence = AsyncMock(), AsyncMock()
    return STORE
