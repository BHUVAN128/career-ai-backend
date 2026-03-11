import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    supabase_user_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False, default="")
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)  # used in local/dev mode
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    roadmaps: Mapped[list["Roadmap"]] = relationship("Roadmap", back_populates="user", cascade="all, delete-orphan")
    chat_sessions: Mapped[list["ChatSession"]] = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    daily_activities: Mapped[list["DailyActivity"]] = relationship("DailyActivity", back_populates="user", cascade="all, delete-orphan")
    streak: Mapped["Streak"] = relationship("Streak", back_populates="user", uselist=False, cascade="all, delete-orphan")
    user_badges: Mapped[list["UserBadge"]] = relationship("UserBadge", back_populates="user", cascade="all, delete-orphan")
    mock_interviews: Mapped[list["MockInterview"]] = relationship("MockInterview", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, default="")
    domain: Mapped[str] = mapped_column(String, default="")
    level: Mapped[str] = mapped_column(String, default="Beginner")  # Beginner/Intermediate/Expert
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    joined_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Diagnosis
    skill_matrix: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON string
    diagnosis_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_text: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")
