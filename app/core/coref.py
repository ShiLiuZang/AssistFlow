import re
from dataclasses import dataclass


ENTITY = re.compile(
    r"(?<![A-Z0-9-])(?:ORD-\d+|MH-[A-Z0-9]+)(?![A-Z0-9-])",
    re.I,
)

REFERENCE = re.compile(
    r"刚才那个订单|那个订单|这个订单|那一单|这单|刚才那个|那个|这个|它"
)

def entities(text):
    return list(
        dict.fromkeys(
            match.upper()
            for match in ENTITY.findall(text)
        )
    )
@dataclass(frozen=True)
class Resolution:
    original: str
    resolved: str
    needs_clarification: bool = False

def resolve(query, history, selected_order=None):
    if not REFERENCE.search(query):
        return Resolution(query, query)

    current = entities(query)

    historical = [
        entity
        for message in history
        if message.type == "human"
        for entity in entities(str(message.content))
    ]

    candidates = current or list(
        dict.fromkeys(
            historical
            + ([selected_order] if selected_order else [])
        )
    )

    if len(candidates) != 1:
        return Resolution(query, query, True)

    rewritten = REFERENCE.sub(
        lambda _: candidates[0],
        query,
    )
    return Resolution(query, rewritten)