from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolContext:
    user_id: str
    conversation_id: str
