from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import LLMError
from app.models.user import User
from app.schemas.chat import SendMessageRequest, SendMessageResponse, ChatMessageSchema
from app.schemas.common import ApiResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/message", response_model=ApiResponse[SendMessageResponse])
async def send_message(
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI mentor and get a response."""
    try:
        response = await chat_service.send_message(
            db=db,
            user_id=current_user.id,
            message=body.message,
            session_id=body.session_id,
            context_step_id=body.context_step_id,
        )
        return ApiResponse.ok(response)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"AI mentor is temporarily unavailable: {str(exc)[:200]}") from exc


@router.get("/history/{session_id}", response_model=ApiResponse[list[ChatMessageSchema]])
async def get_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a session."""
    messages = await chat_service.get_chat_history(db, current_user.id, session_id)
    return ApiResponse.ok(messages)
