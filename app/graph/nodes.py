from app.graph.state import ConversationState


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

    return {
        "retrieve": retrieve,
        "answer": answer,
        "fallback": fallback,
    }