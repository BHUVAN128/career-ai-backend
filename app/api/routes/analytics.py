from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.gamification import Streak
from app.schemas.analytics import WeeklyAnalyticsResponse, AnalyticsSummaryResponse
from app.schemas.common import ApiResponse
from app.services import analytics_engine

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/weekly", response_model=ApiResponse[WeeklyAnalyticsResponse])
async def get_weekly(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get weekly learning performance data."""
    data = await analytics_engine.get_weekly_analytics(db, current_user.id)
    return ApiResponse.ok(data)


@router.get("/summary", response_model=ApiResponse[AnalyticsSummaryResponse])
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get overall analytics summary for the dashboard."""
    streak_result = await db.execute(
        select(Streak).where(Streak.user_id == current_user.id)
    )
    streak = streak_result.scalar_one_or_none()
    streak_count = streak.streak_count if streak else 0
    data = await analytics_engine.get_analytics_summary(db, current_user.id, streak_count)
    return ApiResponse.ok(data)
