"""Agent 决策、工具执行和工单确认节点。"""

from dataclasses import replace

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import interrupt

from app.core.observability import (
    extract_model_name,
    extract_token_usage,
    span,
)
from app.graph.state import ConversationState
from app.tools.audit import build_tool_audit, emit_tool_audit
from app.tools.context import ToolContext
from app.tools.engine import (
    check_tool_call,
    execute_tool_call,
    make_tool_run,
)


def make_agent_nodes(services, update, trace_sink) -> dict:
    """创建工具调用循环节点，共享状态更新和追踪回调。"""
    async def agent(state: ConversationState):
        """
        Agent 工具调用决策节点

        使用 LLM 决策是否需要调用工具，以及调用哪些工具。
        Agent 模式支持多轮工具调用（agent → tools → agent → ...）。

        流程：
        1. 检查步骤数限制（防止无限循环）
        2. 调用 LLM 生成 assistant 消息（可能包含 tool_calls）
        3. 记录 token 用量到追踪 span

        Args:
            state: 对话状态

        Returns:
            状态更新字典，包含新的 assistant 消息
        """
        steps = state.get("steps", 0)

        # 检查步骤数限制
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
        async with span(
            "agent_model",
            trace_sink,
            generation=True,
        ) as record:
            message = await services.agent(
                state.get("messages", []),
                summary_text=state.get("summary_text", ""),
                covered_count=state.get("covered_count", 0),
            )
            usage = extract_token_usage(message)
            model_name = extract_model_name(message)

            if model_name is not None:
                record["model"] = model_name
            if usage is not None:
                record["token_usage"] = usage
        if not isinstance(message, AIMessage):
            raise TypeError("Agent 必须返回 AIMessage")
        if (
            message.invalid_tool_calls
            or any(
                not isinstance(call, dict)
                or not isinstance(call.get("id"), str)
                or not call["id"].strip()
                or not isinstance(call.get("name"), str)
                or not call["name"].strip()
                for call in message.tool_calls
            )
            or len({call["id"] for call in message.tool_calls})
            != len(message.tool_calls)
        ):
            response = AIMessage(content="工具调用格式错误，请稍后重试。")
            return update(
                state,
                "agent",
                messages=[response],
                steps=steps + 1,
                answer=response.content,
            )
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
        validation_errors: dict[str, dict[str, str]] = {}

        verified_order = state.get("last_order_id")
        current_order = state.get("order")

        registry = services.registry
        if registry is None:
            raise RuntimeError("工具注册表未配置")



        for call in calls:
            if call["name"] != "create_ticket":
                continue

            spec, error = check_tool_call(call, registry)
            if error is not None:
                validation_errors[call["id"]] = error
                continue

            if spec.permission != "write":
                validation_errors[call["id"]] = {
                    "code": "permission_denied",
                    "error": "工单工具的权限配置异常",
                }
                continue

            approvals[call["id"]] = interrupt({
                "kind": "confirm_ticket",
                "tool_call_id": call["id"],
                "preview": call["args"],
            })


        for call in calls:
            if call["id"] in validation_errors:
                error = validation_errors[call["id"]]
                run = make_tool_run(
                    call,
                    error["code"],
                    error,
                )

            elif call["name"] == "create_ticket":
                approved = approvals.get(call["id"])

                if (
                    isinstance(approved, dict)
                    and approved.get("tool_call_id") == call["id"]
                    and isinstance(approved.get("tool_result"), dict)
                ):

                    result = approved["tool_result"]

                    if result.get("confirmed") is True:
                        status = "success"
                    elif result.get("confirmed") is False:
                        status = "permission_denied"
                    else:
                        status = "execution_error"
                        result = {
                            "code": "execution_error",
                            "error": "工单确认结果格式异常",
                        }

                    run = make_tool_run(call, status, result)
                else:
                    run = make_tool_run(
                        call,
                        "permission_denied",
                        {
                            "code": "permission_denied",
                            "error": "工单确认结果无效或不匹配",
                        },
                    )

            else:
                context = ToolContext(
                    user_id=state["user_id"],
                    conversation_id=state["conversation_id"],
                )
                async with span("tool_execute", trace_sink) as tool_span:
                    run = await execute_tool_call(
                        call,
                        context,
                        registry,
                        audit_sink=getattr(services, "audit_sink", None),
                    )
                    if not run.ok:
                        tool_span["status"] = "error"
            if call["name"] == "create_ticket":
                approved = approvals.get(call["id"])
                result_from_decision = (
                    call["id"] not in validation_errors
                    and isinstance(approved, dict)
                    and approved.get("tool_call_id") == call["id"]
                    and isinstance(approved.get("tool_result"), dict)
                    and type(approved["tool_result"].get("confirmed")) is bool
                )

                if not result_from_decision:
                    context = ToolContext(
                        user_id=state["user_id"],
                        conversation_id=state["conversation_id"],
                    )
                    record = build_tool_audit(
                        call,
                        context,
                        run,
                        registry.get("create_ticket"),
                    )
                    record = replace(
                        record,
                        audit_key=(
                            f"ticket-node:{state['conversation_id']}:"
                            f"{call['id']}:{run.status}"
                        ),
                    )
                    await emit_tool_audit(
                        getattr(services, "audit_sink", None),
                        record,
                    )

            if (
                    call["name"] == "query_order"
                    and run.ok
                    and run.data.get("found") is True
                    and run.data.get("order_id")
            ):
                verified_order = run.data["order_id"]
                current_order = run.data

            messages.append(
                ToolMessage(
                    content=run.content,
                    tool_call_id=run.tool_call_id,
                    name=run.name,
                    status="success" if run.ok else "error",
                )
            )

        return update(
            state,
            "tools",
            messages=messages,
            last_order_id=verified_order,
            order=current_order,
        )


    return {
        "agent": agent,
        "tools": tools,
    }
