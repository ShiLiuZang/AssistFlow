from typing import Literal

from app.core.llm import get_chat_model
from pydantic import BaseModel
from app.core.retrieval import search_knowledge
class Intent(BaseModel):
    route: Literal[
        "knowledge",
        "business",
        "complaint",
        "chat",
    ]
from app.core.evidence import answer_from_hits
from langchain_core.messages import SystemMessage

from app.core.prompts import CHAT_SYSTEM_PROMPT
from app.tools.order_tools import query_order
from app.tools.ticket_tools import create_ticket
from dataclasses import dataclass
from typing import Callable
from app.core.intent import (
    classify as classify_intent,
    model_predictor,
)

@dataclass
class Services:
    classify: Callable
    retrieve: Callable
    answer: Callable
    agent: Callable
    tools: dict[str, Callable]
    max_steps: int = 3
def make_services() -> Services:
    return Services(
        classify=classify,
        retrieve=retrieve,
        answer=answer,
        agent=agent,
        tools={
            "query_order": order_tool,
            "create_ticket": ticket_tool,
        },
    )
async def order_tool(
    args: dict,
    user_id: str,
    call_id: str,
):
    return await query_order.ainvoke({
        **args,
        "user_id": user_id,
    })
async def ticket_tool(
    args: dict,
    user_id: str,
    call_id: str,
):
    return await create_ticket.ainvoke(args)
async def classify(query: str) -> str:
    model = get_chat_model().with_structured_output(
        Intent,
        method="function_calling",
    )

    result = await model.ainvoke([
        (
            "system",
            "商品与政策咨询归 knowledge；"
            "订单、退款操作归 business；"
            "投诉归 complaint；"
            "闲聊归 chat。",
        ),
        ("human", query),
    ])

    return result.route
async def retrieve(query: str) -> list[dict]:
    return await search_knowledge(
        query,
        strategy="hybrid_rerank",
        top_k=5,
    )



async def answer(query: str, evidence: list[dict]) -> dict:
    return await answer_from_hits(query, evidence)

async def agent(messages):
    model = get_chat_model().bind_tools([
        query_order,
        create_ticket,
    ])

    return await model.ainvoke([
        SystemMessage(content=CHAT_SYSTEM_PROMPT),
        *messages,
    ])
async def classify_detail(query:str):
    model=get_chat_model()
    predict = model_predictor(model)
    return await classify_intent(query, predict)
