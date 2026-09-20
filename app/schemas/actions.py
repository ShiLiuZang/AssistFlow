from pydantic import BaseModel


class ResumeTicketRequest(BaseModel):
    conversation_id: int
    user_id: str
    confirmed: bool
    tool_call_id: str | None = None
