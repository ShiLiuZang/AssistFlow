from langchain_core.messages import HumanMessage
from langgraph.types import Command
from collections.abc import AsyncIterator
from app.core.conversation_lock import conversation_lock


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
            pending = any(task.interrupts for task in snapshot.tasks)

            if resume is None and pending:
                raise ValueError("请先确认或取消待处理操作")

            if resume is not None and not pending:
                raise ValueError("没有待恢复的操作")
            if resume is None and snapshot.next:
                # 执行异常留下的任务可重试，不能误当作人工确认。
                recovered = await self.graph.ainvoke(None, config=config)
                if recovered.get("__interrupt__") or query == snapshot.values.get("query"):
                    return recovered
            if resume is not None:
                payload=Command(resume=resume)
            else:
                payload = {
                    "query": query,
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
