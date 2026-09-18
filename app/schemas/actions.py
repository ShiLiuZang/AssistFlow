from pydantic import BaseModel


class ResumeTicketRequest(BaseModel):
    conversation_id: int
    user_id: str
    confirmed: bool
