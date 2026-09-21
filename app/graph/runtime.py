from langchain_core.messages import HumanMessage
from langgraph.types import Command
from collections.abc import AsyncIterator
from app.core.conversation_lock import conversation_lock
from uuid import uuid4

class Runtime:
    def __init__(self, graph):
        self.graph = graph

    async def run_turn(
            self,
            query: str,
            user_id: str,
            conversation_id: str,
            *,
            resume=None,
    ):
        async with conversation_lock(user_id, conversation_id):
            config={
                "configurable":{
                    "thread_id":f"{user_id}:{conversation_id}",
                },
                "recursion_limit":64
            }
            snapshot = await self.graph.aget_state(config)
            pending = [
                item.value
                for task in snapshot.tasks
                for item in task.interrupts
            ]

            if resume is None and pending:
                raise ValueError("请先确认或取消待处理操作")

            if resume is not None and not pending:
                raise ValueError("没有待恢复的操作")
            if resume is None and snapshot.next:
                if query != snapshot.values.get("query"):
                    raise ValueError("请先重试失败的问题")

                return await self.graph.ainvoke(None, config=config)
            if resume is not None:
                current = pending[0]

                if current.get("kind") == "select_order":
                    if query:
                        raise ValueError("选择订单时不能同时发送新问题")

                    if not isinstance(resume, dict):
                        raise ValueError("选单恢复参数必须是字典")

                    if resume.get("kind") != "select_order":
                        raise ValueError("恢复类型不匹配")

                    if (
                            not current.get("request_id")
                            or resume.get("request_id") != current["request_id"]
                    ):
                        raise ValueError("选单请求已过期或不匹配")

                    cancelled = resume.get("cancelled", False)

                    if type(cancelled) is not bool:
                        raise ValueError("cancelled 必须为布尔值")

                    if cancelled:
                        if resume.get("order_id") is not None:
                            raise ValueError("取消不能同时选择订单")
                    else:
                        selected = resume.get("order_id")
                        offered = {
                            item["order_id"]
                            for item in current["orders"]
                        }

                        if not isinstance(selected, str) or selected not in offered:
                            raise ValueError("必须选择当前卡片中的订单")

                elif (
                        isinstance(resume, dict)
                        and resume.get("kind") == "select_order"
                ):
                    raise ValueError("当前等待的不是订单选择")

                payload = Command(resume=resume)
            else:
                payload = {
                    "query": query,
                    "request_id": uuid4().hex,
                    "route": "",
                    "user_id": user_id,
                    "messages": [HumanMessage(content=query)],
                    "intent": "",
                    "resolved_query": query,
                    "needs_clarification": False,
                    "order": None,
                    "queries": [],
                    "evidence": [],
                    "citations": [],
                    "answer": "",
                    "steps": 0,
                    "trace": [],
                }
            return await self.graph.ainvoke(payload, config=config)

    async def stream_turn(
            self,
            query: str,
            user_id: str,
            conversation_id: str,
            *,
            resume: bool | dict | None = None,
    ) -> AsyncIterator[dict]:
        try:
            result = await self.run_turn(
                query,
                user_id,
                conversation_id,
                resume=resume,
            )

            for name in result.get("trace", []):
                yield {
                    "event": "node",
                    "name": name,
                }

            if result.get("__interrupt__"):
                yield {
                    "event": "interrupt",
                    "preview": result["__interrupt__"][0].value,
                }
                return

            if result.get("citations"):
                yield {
                    "event": "citations",
                    "citations": result["citations"],
                }

            yield {
                "delta": result["answer"],
            }

            yield {
                "event": "done",
            }

        except Exception:
            yield {
                "event": "error",
                "message": "图执行失败",
            }

        finally:
            yield {
                "event": "end",
            }
