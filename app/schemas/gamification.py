from pydantic import BaseModel
from datetime import datetime


class BadgeSchema(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    unlocked: bool
    unlocked_at: datetime | None = None

    class Config:
        from_attributes = True


class StreakSchema(BaseModel):
    streak_count: int
    longest_streak: int
    last_activity_date: str | None
    warning: bool = False


class ProjectSchema(BaseModel):
    id: str
    title: str
    description: str
    difficulty: str
    estimated_hours: int
    skills_used: list[str]
    starter_repo_placeholder: str | None
    completed: bool
    github_url: str | None = None

    class Config:
        from_attributes = True


class SubmitProjectRequest(BaseModel):
    project_id: str
    github_url: str | None = None


class InterviewStartRequest(BaseModel):
    domain: str
    level: str = "Intermediate"


class InterviewAnswerRequest(BaseModel):
    answer: str


class InterviewQuestionSchema(BaseModel):
    id: str
    question: str
    type: str = "behavioral"  # behavioral | technical | situational


class InterviewStartResponse(BaseModel):
    interview_id: str
    question: InterviewQuestionSchema
    question_number: int
    total_questions: int


class InterviewAnswerResponse(BaseModel):
    acknowledged: bool
    next_question: InterviewQuestionSchema | None
    question_number: int
    total_questions: int
    completed: bool


class InterviewResultResponse(BaseModel):
    interview_id: str
    technical_score: float
    clarity_score: float
    confidence_score: float
    completeness_score: float
    overall_score: float
    feedback: str
    transcript: list[dict]


class InternshipSchema(BaseModel):
    id: str
    title: str
    company: str
    domain: str
    location: str
    level: str
    description: str
    required_skills: list[str]
    apply_url: str | None

    class Config:
        from_attributes = True
