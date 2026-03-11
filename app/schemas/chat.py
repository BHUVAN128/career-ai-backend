from pydantic import BaseModel
from datetime import datetime


class SendMessageRequest(BaseModel):
    message: str
    session_id: str | None = None  # will create new session if None
    context_step_id: str | None = None


class ChatMessageSchema(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionSchema(BaseModel):
    id: str
    messages: list[ChatMessageSchema] = []
    created_at: datetime

    class Config:
        from_attributes = True


class SendMessageResponse(BaseModel):
    session_id: str
    message: ChatMessageSchema
    reply: ChatMessageSchema
