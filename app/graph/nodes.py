import json
from dataclasses import replace
from app.core.observability import (
    extract_model_name,
    extract_token_usage,
    span,
)
from langgraph.types import interrupt
from langchain_core.messages import ToolMessage
from app.graph.state import ConversationState
from langchain_core.messages import AIMessage
from app.core.coref import entities, resolve
from app.core.retrieval import retrieve_policy_detailed
from app.tools.context import ToolContext
from app.tools.engine import (
    check_tool_call,
    execute_tool_call,
    make_tool_run,
)
from app.tools.audit import build_tool_audit, emit_tool_audit
from app.config import settings
from app.core.confidence import evidence_gate
from app.db import repository
REFUSAL = "现有知识库没有足够证据确认这个问题，请联系人工客服。"



def make_nodes(services):
    if services.max_steps < 1:
        raise ValueError("max_steps 必须为正数")
    trace_sink = getattr(services, "trace_sink", None)

    def update(state: ConversationState,name:str,**values):
        return {
            "trace":[*state.get("trace",[]),name],
            **values,
        }
    async def assess_evidence(query: str, result: dict) -> dict:
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
        query = state.get("resolved_query") or state["query"]

        retrieve_detailed = getattr(
            services,
            "retrieve_detailed",
            None,
        )
        if not callable(retrieve_detailed):
            raise ValueError("未配置详细检索服务")

        async with span("retrieve", trace_sink):
            result = await retrieve_detailed(query)

        values = await assess_evidence(query, result)

        return update(
            state,
            "retrieve",
            **values,
        )

    async def answer(state: ConversationState):
        query = state.get("resolved_query") or state["query"]
        evidence = state["evidence"]

        async with span("answer", trace_sink):
            result = await services.answer(
                query,
                evidence,
                order=state.get("order"),
                summary_text=state.get("summary_text", ""),
            )

            if not isinstance(result, dict):
                raise ValueError("回答服务必须返回字典")

            refused = result.get("refused")
            if not isinstance(refused, bool):
                raise ValueError("回答服务必须返回布尔值 refused")

            if "reason" not in result:
                raise ValueError("回答服务缺少 reason 字段")

            reason = result["reason"]

            if refused:
                allowed_reasons = {
                    "no_evidence",
                    "unsupported_answer",
                    "grounding_failed",
                }
                if (
                        not isinstance(reason, str)
                        or reason not in allowed_reasons
                ):
                    raise ValueError("回答服务返回了无效的拒答原因")

                source = (
                    "retrieval_low_conf"
                    if reason == "no_evidence"
                    else "self_check"
                )
            else:
                if reason is not None:
                    raise ValueError("正常回答的 reason 必须为 None")

                source = None

                # 保存快照
            message_id = f"msg_{state['conversation_id']}_{state['request_id']}"
            snapshot = state.get("retrieved_snapshot")
            turn_saved = False

            try:
                await repository.save_turn(
                    owner=state["user_id"],
                    conversation=str(state["conversation_id"]),
                    message_id=message_id,
                    turn_id=state["request_id"],
                    question=query,
                    snapshot=snapshot,
                )
                turn_saved = True
            except Exception as e:
                # 快照保存失败不影响回答返回
                # 但应该记录日志（这里简化处理）
                pass

            # 如果拒答，自动落池
            if refused and source and turn_saved:
                try:
                    await repository.capture_low_confidence(
                        owner=state["user_id"],
                        conversation=str(state["conversation_id"]),
                        message_id=message_id,
                        source=source,
                        reason=reason,
                    )
                except Exception as e:
                    # 落池失败不影响回答返回
                    pass

            return update(
                state,
                "answer",
                answer=REFUSAL if refused else result["answer"],
                citations=[] if refused else result["citations"],
                fallback_source=source,
                fallback_reason=reason,
                message_id=message_id if turn_saved else None,
            )
    async def fallback(state: ConversationState):
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
        turn_saved = False

        try:
            await repository.save_turn(
                owner=state["user_id"],
                conversation=str(state["conversation_id"]),
                message_id=message_id,
                turn_id=state["request_id"],
                question=query,
                snapshot=snapshot,
            )
            turn_saved = True
        except Exception as e:
            pass

        # 自动落池
        if turn_saved:
            try:
                await repository.capture_low_confidence(
                    owner=state["user_id"],
                    conversation=str(state["conversation_id"]),
                    message_id=message_id,
                    source=source,
                    reason=reason,
                )
            except Exception as e:
                pass

        return update(
            state,
            "fallback",
            answer=answer,
            citations=[],
            message_id=message_id if turn_saved else None,
        )

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

        # 第一轮只准备工单确认。
        # interrupt 恢复会从节点开头重跑，因此这里不执行业务处理器。
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

        # 第二轮为每个调用生成对应结果。
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
                    # 只消费服务端确认入口回传的已保存决定，不再次执行工具。
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
    async def classify(state: ConversationState):
        messages = state.get("messages", [])
        covered_count = state.get("covered_count", 0)
        uncovered = messages[covered_count:]
        recent_context = [
            {"role": message.type, "content": str(message.content)[:800]}
            for message in uncovered[:-1]  # 最后一条是本轮问题，下面单独传
            if message.type in {"human", "ai"} and message.content
        ][-4:]
        async with span("classify", trace_sink) as record:
            prediction, route = await services.classify(
                state.get("resolved_query") or state["query"],
                summary_text=state.get("summary_text", ""),
                recent_context=recent_context,
            )
            record["intent"] = prediction.intent.value
            record["intent_confidence"] = prediction.confidence
        legacy = {
            "knowledge": "knowledge",
            "business": "business",
            "refund": "business",
            "complaint": "complaint",
            "human": "chat",
            "chat": "chat",
            "clarify": "chat",
        }

        return update(
            state,
            "classify",
            intent=legacy[route],
            intent_detail=prediction.intent.value,
            intent_confidence=prediction.confidence,
            route=route,
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
        messages = state.get("messages", [])
        covered_count = state.get("covered_count", 0)
        if not 0 <= covered_count <= len(messages):
            raise ValueError("摘要覆盖条数超出图消息范围")

        result = resolve(
            state["query"],
            messages[covered_count:],
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
    async def clarify_reference(state: ConversationState):
        return update(
            state,
            "clarify_reference",
            answer="请说明你指的是哪个订单或商品。",
            citations=[],
        )

    async def order_result(state: ConversationState):
        answers = {
            "clarify": "请一次只提供一个订单号。",
            "no_orders": "没有查到你当前可选择的订单。",
            "cancelled": "已取消选择订单，本次没有继续处理。",
            "not_owned": "没有找到属于你的这笔订单，请核对订单号。",
        }

        answer = answers.get(
            state.get("route"),
            "暂时无法确认订单，请稍后重试。",
        )

        return update(
            state,
            "order_result",
            answer=answer,
            citations=[],
        )
    async def human(state: ConversationState):
        return update(
            state,
            "human",
            answer="如需人工协助，请通过订单售后入口联系人工客服。",
            citations=[],
        )

    async def clarify_intent(state: ConversationState):
        return update(
            state,
            "clarify_intent",
            answer="请补充你希望办理的事情，例如查询订单、咨询商品或申请售后。",
            citations=[],
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
            answer=state.get("answer","")
            history = state.get("messages",[])
            last_message=history[-1] if history else None
            answer_already_present=(
                getattr(last_message,"type",None)=="ai"
                and str(last_message.content)==answer
            )
            if answer and not answer_already_present:
                messages = [
                    AIMessage(
                        content=answer,
                        id=state.get("message_id"),
                    )
                ]
        else:
            messages = [
                AIMessage(
                    content=state["answer"],
                    id=state.get("message_id"),
                )
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
        "clarify_reference": clarify_reference,
        "order_result": order_result,
        "human": human,
        "clarify_intent": clarify_intent,
    }
