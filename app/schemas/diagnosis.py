from pydantic import BaseModel
from typing import Any


class DiagnosisResumeRequest(BaseModel):
    """Used when diagnosis is done via text (resume content passed as text)."""
    resume_text: str


class AssessmentStartRequest(BaseModel):
    level: str  # Beginner / Intermediate / Expert
    domain: str


class AssessmentSubmitRequest(BaseModel):
    answers: list[dict]  # [{question_id, answer}]
    level: str
    domain: str


class SkillMatrix(BaseModel):
    skill: str
    score: int  # 0-100


class DiagnosisResult(BaseModel):
    detected_level: str
    recommended_domain: str
    skill_matrix: list[SkillMatrix]
    summary: str
    weaknesses: list[str] = []          # honest skill gaps identified
    available_domains: list[str] = []   # domains this profile could work in


class AssessmentQuestion(BaseModel):
    id: str
    question: str
    type: str  # mcq | scenario | practical
    options: list[str] | None = None
    difficulty: str


class AssessmentQuestionsResponse(BaseModel):
    questions: list[AssessmentQuestion]
    level: str
    domain: str
    layer: int  # 1=MCQ, 2=Scenario, 3=Practical
