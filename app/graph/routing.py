from typing import Literal



from .state import ConversationState


def route_by_intent(
    state: ConversationState,
) -> Literal["knowledge", "business", "complaint", "chat"]:
    intent = state.get("intent")

    if intent in ["knowledge", "business", "complaint", "chat"]:
        return intent

    return "chat"
def confidence_gate(state:ConversationState)->Literal["answer", "fallback"]:
    evidence = state.get("evidence")
    if evidence:
        return "answer"

    return "fallback"

def should_continue(state:ConversationState)->Literal["tools", "finish"]:
   messages= state.get("messages")
   if not messages:
       return "finish"
   last_message= messages[-1]
   tool_call=getattr(last_message, "tool_calls",[])
   if tool_call:
        return "tools"
   return "finish"
