import json
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.analytics import DailyActivity, WeeklyStats, SkillScore
from app.models.roadmap import Roadmap, StepSubmission
from app.schemas.analytics import (
    DailyDataPoint, SkillScoreSchema, WeeklySummary,
    WeeklyAnalyticsResponse, AnalyticsSummaryResponse,
)


DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


async def get_weekly_analytics(db: AsyncSession, user_id: str) -> WeeklyAnalyticsResponse:
    """Calculate weekly learning analytics."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Fetch daily activities for the week
    activities_result = await db.execute(
        select(DailyActivity)
        .where(
            and_(
                DailyActivity.user_id == user_id,
                DailyActivity.activity_date >= week_start,
                DailyActivity.activity_date <= week_end,
            )
        )
    )
    activities = {a.activity_date: a for a in activities_result.scalars().all()}

    daily_data: list[DailyDataPoint] = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        activity = activities.get(day_date)
        daily_data.append(DailyDataPoint(
            day=DAYS[i],
            date=day_date.isoformat(),
            score=float(activity.quiz_accuracy or 0) if activity else 0.0,
            hours=round((activity.time_spent_minutes or 0) / 60, 1) if activity else 0.0,
            steps_completed=activity.steps_completed if activity else 0,
        ))

    # Weekly summary
    total_steps = sum(d.steps_completed for d in daily_data)
    total_hours = sum(d.hours for d in daily_data)
    accuracy_scores = [d.score for d in daily_data if d.score > 0]
    avg_accuracy = sum(accuracy_scores) / len(accuracy_scores) if accuracy_scores else 0

    # Roadmap completion
    roadmap_result = await db.execute(
        select(Roadmap).where(Roadmap.user_id == user_id, Roadmap.is_active == True)
    )
    roadmap = roadmap_result.scalar_one_or_none()
    completion_pct = 0.0
    if roadmap and roadmap.total_steps > 0:
        completion_pct = round(roadmap.completed_steps / roadmap.total_steps * 100, 1)

    # Skill scores
    skill_scores = await get_skill_scores(db, user_id)
    weakest = min(skill_scores, key=lambda s: s.score).skill if skill_scores else None

    summary = WeeklySummary(
        completion_percent=completion_pct,
        accuracy_percent=round(avg_accuracy, 1),
        skill_growth_delta={},
        weakest_skill=weakest,
        learning_velocity=round(total_steps / 7, 2),
        total_minutes=int(total_hours * 60),
        week_start=week_start.isoformat(),
    )

    return WeeklyAnalyticsResponse(
        daily_data=daily_data,
        summary=summary,
        skill_scores=skill_scores,
    )


async def get_skill_scores(db: AsyncSession, user_id: str) -> list[SkillScoreSchema]:
    """Get skill scores for a user."""
    result = await db.execute(
        select(SkillScore).where(SkillScore.user_id == user_id)
    )
    scores = result.scalars().all()
    return [SkillScoreSchema(skill=s.skill, score=s.score, max_score=s.max_score) for s in scores]


async def get_analytics_summary(db: AsyncSession, user_id: str, streak_count: int) -> AnalyticsSummaryResponse:
    """Get overall platform analytics summary."""
    weekly = await get_weekly_analytics(db, user_id)

    # All activities
    all_activities = await db.execute(
        select(DailyActivity).where(DailyActivity.user_id == user_id)
    )
    activities = all_activities.scalars().all()
    total_minutes = sum(a.time_spent_minutes for a in activities)

    # All submissions for accuracy
    all_submissions = await db.execute(
        select(StepSubmission).where(StepSubmission.user_id == user_id)
    )
    submissions = all_submissions.scalars().all()
    if submissions:
        scores = [s.score for s in submissions if s.score is not None]
        avg_accuracy = sum(scores) / len(scores) if scores else 0
    else:
        avg_accuracy = 0

    roadmap_result = await db.execute(
        select(Roadmap).where(Roadmap.user_id == user_id, Roadmap.is_active == True)
    )
    roadmap = roadmap_result.scalar_one_or_none()
    completion_rate = 0.0
    if roadmap and roadmap.total_steps > 0:
        completion_rate = round(roadmap.completed_steps / roadmap.total_steps * 100, 1)

    return AnalyticsSummaryResponse(
        completion_rate=completion_rate,
        practice_accuracy=round(avg_accuracy, 1),
        total_focus_minutes=total_minutes,
        current_streak=streak_count,
        skills=weekly.skill_scores,
        weekly_history=[weekly.summary],
    )


async def log_activity(
    db: AsyncSession,
    user_id: str,
    steps_completed: int = 0,
    time_spent_minutes: int = 0,
    quiz_accuracy: float | None = None,
):
    """Log or update today's activity."""
    today = date.today()
    result = await db.execute(
        select(DailyActivity)
        .where(DailyActivity.user_id == user_id, DailyActivity.activity_date == today)
    )
    activity = result.scalar_one_or_none()

    if activity:
        activity.steps_completed += steps_completed
        activity.time_spent_minutes += time_spent_minutes
        if quiz_accuracy is not None:
            # Running average
            if activity.quiz_accuracy is not None:
                activity.quiz_accuracy = (activity.quiz_accuracy + quiz_accuracy) / 2
            else:
                activity.quiz_accuracy = quiz_accuracy
    else:
        activity = DailyActivity(
            user_id=user_id,
            activity_date=today,
            steps_completed=steps_completed,
            time_spent_minutes=time_spent_minutes,
            quiz_accuracy=quiz_accuracy,
        )
        db.add(activity)

    await db.commit()


async def update_skill_scores(db: AsyncSession, user_id: str, skill_updates: dict):
    """Update or create skill scores."""
    for skill, score in skill_updates.items():
        result = await db.execute(
            select(SkillScore)
            .where(SkillScore.user_id == user_id, SkillScore.skill == skill)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.score = float(score)
        else:
            db.add(SkillScore(user_id=user_id, skill=skill, score=float(score)))
    await db.commit()
