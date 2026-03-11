import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[str] = mapped_column(String, default="Beginner")
    estimated_hours: Mapped[int] = mapped_column(Integer, default=10)
    skills_used: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    starter_repo_placeholder: Mapped[str | None] = mapped_column(String, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    github_url: Mapped[str | None] = mapped_column(String, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MockInterview(Base):
    __tablename__ = "mock_interviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, default="Intermediate")
    questions: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of questions
    current_question_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="in_progress")  # in_progress | completed
    # Scores (0-10 each)
    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    clarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of {question, answer}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="mock_interviews")


class Internship(Base):
    __tablename__ = "internships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, default="Remote")
    level: Mapped[str] = mapped_column(String, default="Beginner")
    description: Mapped[str] = mapped_column(Text, default="")
    required_skills: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    apply_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
