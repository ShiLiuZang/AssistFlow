import json
from logging import exception

from langchain_core.messages import ToolMessage
from app.graph.state import ConversationState
from langchain_core.messages import AIMessage

REFUSAL = "现有知识库没有足够证据确认这个问题，请联系人工客服。"



def make_nodes(services):
    def update(state: ConversationState,name:str,**values):
        return {
            "trace":[*state.get("trace",[]),name],
            **values,
        }

    async def retrieve(state: ConversationState):
        # 读取 query
        query = state["query"]

        # 调用检索服务
        hits = await services.retrieve(query)

        # 返回 evidence 和 trace
        return update(state, "retrieve", evidence=hits)

    async def answer(state: ConversationState):
        # 读取 query、evidence
        query = state["query"]
        evidence = state["evidence"]
        # 调用 services.answer
        result= await services.answer(query, evidence)
        # 返回 answer、citations 和 trace
        return update(state, "answer",answer=result["answer"],
        citations=result["citations"])



    async def fallback(state: ConversationState):
        # 不调用服务
        # 返回固定拒答、空 citations 和 trace
        return update(state, "fallback", answer=REFUSAL,citations=[])

    async def agent(state: ConversationState):
        steps = state.get("steps", 0)

        if steps >= services.max_steps:
            message = AIMessage(
                content="工具调用已达上限，请补充信息或联系人工客服。"
            )

            return update(
                state,
                "agent",
                messages=[message],
                answer=message.content,
            )

        message = await services.agent(
            state.get("messages", [])
        )

        if not isinstance(message, AIMessage):
            raise TypeError("Agent 必须返回 AIMessage")

        return update(
            state,
            "agent",
            messages=[message],
            steps=steps + 1,
            answer="" if message.tool_calls else str(message.content),
        )

    async def tools(state: ConversationState):
        calls = state["messages"][-1].tool_calls
        messages = []

        for call in calls:
            try:
                if call["name"] not in services.tools:
                    result = {"error": "未知工具"}
                else:
                    result = await services.tools[call["name"]](
                        call["args"],
                        state["user_id"],
                        call["id"],
                    )
            except Exception:
                result = {"error": "工具执行失败"}

            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call["id"],
                    name=call["name"],
                )
            )

        return update(
            state,
            "tools",
            messages=messages,
        )
    return {
        "retrieve": retrieve,
        "answer": answer,
        "fallback": fallback,
        "agent": agent,
        "tools": tools,

    }
