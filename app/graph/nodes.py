import json
from langgraph.types import interrupt
from langchain_core.messages import ToolMessage
from app.graph.state import ConversationState
from langchain_core.messages import AIMessage
from app.core.coref import entities, resolve
from app.core.retrieval import retrieve_policy
REFUSAL = "现有知识库没有足够证据确认这个问题，请联系人工客服。"



def make_nodes(services):
    if services.max_steps < 1:
        raise ValueError("max_steps 必须为正数")

    def update(state: ConversationState,name:str,**values):
        return {
            "trace":[*state.get("trace",[]),name],
            **values,
        }

    async def retrieve(state: ConversationState):
        # 读取 query
        query = state.get("resolved_query") or state["query"]

        # 调用检索服务
        hits = await services.retrieve(query)

        # 返回 evidence 和 trace
        return update(state, "retrieve", evidence=hits)

    async def answer(state: ConversationState):
        # 读取 query、evidence
        query = state.get("resolved_query") or state["query"]
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
        approvals = {}
        verified_order = state.get("last_order_id")
        current_order = state.get("order")
        # 先收集每个调用的确认，再执行工具；恢复会从节点开头重跑。
        for call in calls:
            if call["name"] == "create_ticket" and call["name"] in services.tools:
                approvals[call["id"]] = interrupt({
                    "kind": "confirm_ticket",
                    "tool_call_id": call["id"],
                    "preview": call["args"],
                })
        for call in calls:
            approved = approvals.get(call["id"], False)
            try:
                if call["name"] not in services.tools:
                    result = {"error": "未知工具"}
                elif (
                    call["name"] == "create_ticket"
                    and isinstance(approved, dict)
                    and approved.get("tool_call_id") == call["id"]
                    and "tool_result" in approved
                ):
                    result = approved["tool_result"]
                elif call["name"] == "create_ticket" and approved is not True:
                    result = {"cancelled": True}
                else:
                    result = await services.tools[call["name"]](
                        call["args"],
                        state["user_id"],
                        call["id"],
                    )

            except Exception:
                result = {"error": "工具执行失败"}
            if (
                call["name"] == "query_order"
                and isinstance(result, dict)
                and result.get("found") is True
                and result.get("order_id")
            ):
                verified_order = result["order_id"]
                current_order = result
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
            last_order_id=verified_order,
            order=current_order,
        )
    async def classify(state: ConversationState):
        intent=await services.classify(
            state.get("resolved_query") or state["query"]
        )
        return update(
            state,
            "classify",
            intent=intent,
        )
    async def chat(state: ConversationState):
        return update(
            state,
            "chat",
            answer="你好，可以咨询商品知识、订单或售后问题。"
        )
    async def complaint(state: ConversationState):
        return update(
            state,
            "complaint",
            answer="已了解你的投诉，请通过订单售后入口联系人工客服处理。",
        )
    async def resolve_reference(state: ConversationState):
        result = resolve(
            state["query"],
            state.get("messages", []),
            state.get("last_order_id") or state.get("selected_order"),
        )
        return update(
            state,
            "resolve_reference",
            query=result.original,
            resolved_query=result.resolved,
            needs_clarification=result.needs_clarification,
        )
    async def fetch_order(state: ConversationState):
        ids = [
            value
            for value in entities(state.get("resolved_query", state["query"]))
            if value.startswith("ORD-")
        ]

        if len(ids) > 1:
            return update(
                state,
                "fetch_order",
                order=None,
                route="clarify",
            )

        if ids:
            selected = ids[0]
        else:
            orders = await services.list_orders(state["user_id"])

            if not orders:
                return update(
                    state,
                    "fetch_order",
                    order=None,
                    route="no_orders",
                )

            choice = interrupt({
                "kind": "select_order",
                "request_id": state["request_id"],
                "orders": [
                    {
                        "order_id": item["order_id"],
                        "product_name": item["product_name"],
                    }
                    for item in orders
                ],
            })

            if choice.get("cancelled") is True:
                return update(
                    state,
                    "fetch_order",
                    order=None,
                    route="cancelled",
                )

            selected = choice.get("order_id")

            if selected not in {item["order_id"] for item in orders}:
                return update(
                    state,
                    "fetch_order",
                    order=None,
                    route="not_owned",
                )

        order = await services.get_order(selected)

        if (
            not order
            or order.get("user_id") != state["user_id"]
            or order.get("order_id") != selected
        ):
            return update(
                state,
                "fetch_order",
                order=None,
                route="not_owned",
            )

        return update(
            state,
            "fetch_order",
            order=dict(order),
            last_order_id=selected,
            route="policy",
        )
    async def policy(state: ConversationState):
        expand = getattr(services, "expand_policy", None)
        if expand is None:
            async def expand(_query):
                return []
        queries, citations = await retrieve_policy(
            state.get("resolved_query", state["query"]),
            state.get("order"),
            expand,
            services.retrieve,
        )
        return update(
            state,
            "policy",
            queries=queries,
            citations=citations,
            evidence=citations,
        )
    async def finish(state: ConversationState):
        if state.get("intent") == "business":
            messages = []
            decisions = []
            for message in reversed(state.get("messages", [])):
                if message.type == "human":
                    break
                if message.type == "tool":
                    result = json.loads(message.content)
                    if isinstance(result, dict) and "confirmed" in result:
                        decisions.append(
                            f"工单已创建，工单号：{result['ticket_no']}"
                            if result["confirmed"] else "已取消，本次没有创建工单。"
                        )
            if decisions:
                # 已持久化的业务决定是最终事实，不能被模型改写成再次确认。
                answer = "\n".join(reversed(decisions))
                messages = [AIMessage(content=answer, id=state["messages"][-1].id)]
                return update(state, "finish", messages=messages, answer=answer)
        else:
            messages = [
                AIMessage(content=state["answer"])
            ]

        return update(
            state,
            "finish",
            messages=messages,
        )
    return {
        "retrieve": retrieve,
        "answer": answer,
        "fallback": fallback,
        "agent": agent,
        "tools": tools,
        "complaint": complaint,
        "chat": chat,
        "classify": classify,
        "finish": finish,
        "resolve_reference": resolve_reference,
        "fetch_order": fetch_order,
        "policy": policy,
    }
