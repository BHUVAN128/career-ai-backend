from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.gamification import Streak
from app.schemas.gamification import StreakSchema


async def get_or_create_streak(db: AsyncSession, user_id: str) -> Streak:
    result = await db.execute(select(Streak).where(Streak.user_id == user_id))
    streak = result.scalar_one_or_none()
    if not streak:
        streak = Streak(user_id=user_id, streak_count=0, longest_streak=0)
        db.add(streak)
        await db.commit()
        await db.refresh(streak)
    return streak


async def update_streak(db: AsyncSession, user_id: str) -> Streak:
    """Update streak based on today's activity."""
    streak = await get_or_create_streak(db, user_id)
    today = date.today()

    if streak.last_activity_date is None:
        # First activity ever
        streak.streak_count = 1
        streak.last_activity_date = today
        streak.warning_sent = False
    elif streak.last_activity_date == today:
        # Already updated today, no change
        pass
    elif streak.last_activity_date == today - timedelta(days=1):
        # Consecutive day — increment
        streak.streak_count += 1
        streak.last_activity_date = today
        streak.warning_sent = False
    elif streak.last_activity_date == today - timedelta(days=2):
        # 2 days gap — reset
        streak.streak_count = 1
        streak.last_activity_date = today
        streak.warning_sent = False
    else:
        # More than 2 days missed — reset
        streak.streak_count = 1
        streak.last_activity_date = today
        streak.warning_sent = False

    if streak.streak_count > streak.longest_streak:
        streak.longest_streak = streak.streak_count

    await db.commit()
    await db.refresh(streak)
    return streak


async def get_streak_status(db: AsyncSession, user_id: str) -> StreakSchema:
    streak = await get_or_create_streak(db, user_id)
    today = date.today()

    warning = False
    if streak.last_activity_date:
        days_since = (today - streak.last_activity_date).days
        if days_since == 1:
            warning = True  # Will lose streak tomorrow

    return StreakSchema(
        streak_count=streak.streak_count,
        longest_streak=streak.longest_streak,
        last_activity_date=streak.last_activity_date.isoformat() if streak.last_activity_date else None,
        warning=warning,
    )
