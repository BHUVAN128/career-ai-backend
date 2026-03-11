import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, Date, DateTime, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class DailyActivity(Base):
    __tablename__ = "daily_activities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    time_spent_minutes: Mapped[int] = mapped_column(Integer, default=0)
    quiz_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="daily_activities")


class WeeklyStats(Base):
    __tablename__ = "weekly_stats"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    completion_percent: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy_percent: Mapped[float] = mapped_column(Float, default=0.0)
    skill_growth_delta: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    weakest_skill: Mapped[str | None] = mapped_column(String, nullable=True)
    learning_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    total_minutes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillScore(Base):
    __tablename__ = "skill_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    skill: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=100.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
