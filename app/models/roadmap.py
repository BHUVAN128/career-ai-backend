import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Roadmap(Base):
    __tablename__ = "roadmaps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, default="")
    domain: Mapped[str] = mapped_column(String, default="")
    level: Mapped[str] = mapped_column(String, default="Beginner")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="roadmaps")
    phases: Mapped[list["Phase"]] = relationship("Phase", back_populates="roadmap", cascade="all, delete-orphan", order_by="Phase.order_index")


class Phase(Base):
    __tablename__ = "phases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    roadmap_id: Mapped[str] = mapped_column(String, ForeignKey("roadmaps.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    roadmap: Mapped["Roadmap"] = relationship("Roadmap", back_populates="phases")
    steps: Mapped[list["Step"]] = relationship("Step", back_populates="phase", cascade="all, delete-orphan", order_by="Step.order_index")


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phase_id: Mapped[str] = mapped_column(String, ForeignKey("phases.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, default="")
    description: Mapped[Text] = mapped_column(Text, default="")
    step_type: Mapped[str] = mapped_column(String, default="reading")  # video|reading|quiz|coding|project|reflection
    status: Mapped[str] = mapped_column(String, default="locked")  # locked|active|completed
    difficulty: Mapped[str] = mapped_column(String, default="Beginner")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    unlock_condition: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "prev_step_completed"
    content_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: video_url, quiz_questions, etc.
    resources: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of links
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    phase: Mapped["Phase"] = relationship("Phase", back_populates="steps")
    submissions: Mapped[list["StepSubmission"]] = relationship("StepSubmission", back_populates="step", cascade="all, delete-orphan")


class StepSubmission(Base):
    __tablename__ = "step_submissions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    step_id: Mapped[str] = mapped_column(String, ForeignKey("steps.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    submission_type: Mapped[str] = mapped_column(String, default="quiz")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: submitted answers/code/text
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI-generated feedback JSON
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    step: Mapped["Step"] = relationship("Step", back_populates="submissions")
