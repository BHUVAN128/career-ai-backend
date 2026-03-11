import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Boolean, Integer, Float, Text, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String, default="star")
    condition_type: Mapped[str] = mapped_column(String, default="steps_completed")  # steps_completed|streak|accuracy|projects
    condition_value: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user_badges: Mapped[list["UserBadge"]] = relationship("UserBadge", back_populates="badge")


class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    badge_id: Mapped[str] = mapped_column(String, ForeignKey("badges.id"), index=True, nullable=False)
    unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="user_badges")
    badge: Mapped["Badge"] = relationship("Badge", back_populates="user_badges")


class Streak(Base):
    __tablename__ = "streaks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, index=True, nullable=False)
    streak_count: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warning_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="streak")
