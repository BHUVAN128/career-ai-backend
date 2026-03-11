import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm.factory import get_llm_provider
from app.models.chat import ChatSession, ChatMessage
from app.models.user import UserProfile
from app.schemas.chat import SendMessageResponse, ChatMessageSchema


MENTOR_SYSTEM_PROMPT = """You are CareerAI Mentor — an expert AI career coaching assistant.

Your personality:
- Encouraging, professional, and knowledgeable
- Personalized and context-aware
- Focused on practical, actionable advice
- Supportive when users struggle, challenging when they need to grow

You have access to the user's:
- Current learning domain and level
- Active roadmap step
- Recent performance

Provide concise, helpful responses. Use bullet points for lists.
When explaining technical concepts, give practical examples.
Always encourage continued learning."""


async def get_or_create_session(
    db: AsyncSession,
    user_id: str,
    session_id: str | None = None,
    context_step_id: str | None = None,
) -> ChatSession:
    if session_id:
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    session = ChatSession(
        user_id=user_id,
        context_step_id=context_step_id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def send_message(
    db: AsyncSession,
    user_id: str,
    message: str,
    session_id: str | None = None,
    context_step_id: str | None = None,
) -> SendMessageResponse:
    """Process a user message and return AI response."""
    session = await get_or_create_session(db, user_id, session_id, context_step_id)

    # Get user profile for context
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    # Build context system prompt
    context_parts = [MENTOR_SYSTEM_PROMPT]
    if profile:
        context_parts.append(
            f"\nUser context: {profile.name or 'Student'} is studying {profile.domain or 'programming'} "
            f"at {profile.level or 'Beginner'} level."
        )
    if context_step_id:
        context_parts.append(f"\nThe user is currently working on step ID: {context_step_id}")

    system_prompt = "\n".join(context_parts)

    # Get recent chat history (last 10 messages for context window)
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    history = list(reversed(history_result.scalars().all()))

    # Format for LLM
    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": message})

    # Store user message
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=message,
    )
    db.add(user_message)
    await db.flush()

    # Generate AI response
    llm = get_llm_provider()
    ai_response_text = await llm.generate_chat(
        messages=messages,
        system_prompt=system_prompt,
    )

    # Store AI response
    ai_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=ai_response_text,
    )
    db.add(ai_message)
    await db.commit()
    await db.refresh(user_message)
    await db.refresh(ai_message)

    return SendMessageResponse(
        session_id=session.id,
        message=ChatMessageSchema(
            id=user_message.id,
            role=user_message.role,
            content=user_message.content,
            created_at=user_message.created_at,
        ),
        reply=ChatMessageSchema(
            id=ai_message.id,
            role=ai_message.role,
            content=ai_message.content,
            created_at=ai_message.created_at,
        ),
    )


async def get_chat_history(
    db: AsyncSession,
    user_id: str,
    session_id: str,
) -> list[ChatMessageSchema]:
    result = await db.execute(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatSession.user_id == user_id, ChatSession.id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    return [ChatMessageSchema(
        id=m.id, role=m.role, content=m.content, created_at=m.created_at
    ) for m in messages]
