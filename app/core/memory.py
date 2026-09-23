import json
from dataclasses import dataclass

@dataclass(frozen=True)
class Message:
    id: int
    role: str
    content: str
    calls: tuple[str, ...] = ()
    call_id: str | None = None

def group_turns(messages):
    groups=[]
    current=[]
    for message in messages:
        role=message.role
        if role == "human" and current:
            groups.append(current)
            current=[]
        current.append(message)
    if current:
        groups.append(current)
    return groups
def estimate(messages):
    return sum(
        len(json.dumps(message.__dict__, ensure_ascii=False)) + 8
        for message in messages
    )
def turns(messages):
    groups=[]
    pending=set()
    previous=0
    for message in messages:
        if message.id <= previous:
            raise ValueError("message IDs must increase")
        previous=message.id
        if message.role=="human":
            if pending:
                raise ValueError("unfinished tool calls")
            groups.append([])
        elif message.role=="tool":
            if message.call_id not in pending:
                raise ValueError("orphan or duplicate tool result")
            pending.remove(message.call_id)
        elif message.role == "ai":
            if pending:
                raise ValueError("tool results missing")
            if len(set(message.calls)) != len(message.calls):
                raise ValueError("duplicate call IDs")
            pending.update(message.calls)
        else:
            raise ValueError("history only accepts human/ai/tool")

        if not groups:
            raise ValueError("history must begin with human")
        groups[-1].append(message)
    if pending:
        raise ValueError("finish tool execution before model input")

    return groups

def build_window(messages, budget, reserve=0, keep=3, count=estimate):
    if budget <= reserve or reserve < 0 or keep < 1:
        raise ValueError("invalid budget or window")

    groups = turns(messages)
    result = []
    for group in reversed(groups[-keep:]):
        candidate = group + result
        if count(candidate) + reserve > budget:
            if not result:
                raise ValueError("current turn exceeds budget")
            break
        result = candidate
    return result
