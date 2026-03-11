from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.gamification import (
    InterviewStartRequest, InterviewAnswerRequest,
    InterviewStartResponse, InterviewAnswerResponse,
    InterviewResultResponse,
)
from app.schemas.common import ApiResponse
from app.services import interview_engine

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/start", response_model=ApiResponse[InterviewStartResponse])
async def start_interview(
    body: InterviewStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Begin a new mock interview session."""
    result = await interview_engine.start_interview(
        db=db, user_id=current_user.id,
        domain=body.domain, level=body.level,
    )
    return ApiResponse.ok(result)


@router.post("/{interview_id}/answer", response_model=ApiResponse[InterviewAnswerResponse])
async def answer_question(
    interview_id: str,
    body: InterviewAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer and get the next question (or completion signal)."""
    try:
        result = await interview_engine.process_answer(
            db=db, interview_id=interview_id,
            user_id=current_user.id, answer=body.answer,
        )
        return ApiResponse.ok(result)
    except ValueError as e:
        return ApiResponse.fail(str(e))


@router.get("/{interview_id}/result", response_model=ApiResponse[InterviewResultResponse])
async def get_result(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the final scored result for a completed interview."""
    try:
        result = await interview_engine.get_interview_result(
            db=db, interview_id=interview_id, user_id=current_user.id,
        )
        return ApiResponse.ok(result)
    except ValueError as e:
        return ApiResponse.fail(str(e))
