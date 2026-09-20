from langchain_core.messages import HumanMessage
from langgraph.types import Command



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
        config={
            "configurable":{
                "thread_id":f"{user_id}:{conversation_id}",
            },
            "recursion_limit":64
        }
        snapshot = await self.graph.aget_state(config)
        pending = bool(snapshot.next)

        if resume is None and pending:
            raise ValueError("请先确认或取消待处理操作")

        if resume is not None and not pending:
            raise ValueError("没有待恢复的操作")
        if resume is not None:
            payload=Command(resume=resume)
        else:
            payload = {
                "query": query,
                "user_id": user_id,
                "messages": [HumanMessage(content=query)],
                "intent": "",
                "evidence": [],
                "answer": "",
                "citations": [],
                "steps": 0,
                "trace": [],
            }
        return await self.graph.ainvoke(payload, config=config)
