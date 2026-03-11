import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    context_step_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("chat_sessions.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String, default="user")  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
