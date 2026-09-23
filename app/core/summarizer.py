from app.core.memory import turns
import asyncio
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class Summary:
    text: str = ""
    upto: int = 0

class SummaryStore:
    def __init__(self):
        self.records = {}
        self.lock={}

    async def update(
            self,
            key,
            messages,
            summarize,
            keep=2,
            threshold=1,
    ):
        async with self.lock.setdefault(key, asyncio.Lock()):
            old =self.records.get(key,Summary())
            new = await summarize_delta(
                old,
                messages,
                summarize,
                keep=keep,
                threshold=threshold,
            )
            self.records[key] = new
            return new
def compute_boundary(messages, keep=2):
    if keep < 1:
        raise ValueError("retain at least the current turn")
    groups = turns(messages)
    if len(groups) <=keep:
        return 0
    return groups[-keep-1][-1].id



async def summarize_delta(old, messages, summarize, keep=2, threshold=1):
    boundary = compute_boundary(messages, keep=keep)
    delta=[message for message in messages  if old.upto < message.id <= boundary]
    if len(delta) < threshold:
        return old
    text = await summarize(old.text, tuple(delta))
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty summary")
    return Summary(text.strip(), boundary)
