from pydantic import BaseModel
from datetime import date


class DailyDataPoint(BaseModel):
    day: str  # Mon, Tue, etc.
    date: str
    score: float
    hours: float
    steps_completed: int


class SkillScoreSchema(BaseModel):
    skill: str
    score: float
    max_score: float = 100.0


class WeeklySummary(BaseModel):
    completion_percent: float
    accuracy_percent: float
    skill_growth_delta: dict
    weakest_skill: str | None
    learning_velocity: float
    total_minutes: int
    week_start: str


class WeeklyAnalyticsResponse(BaseModel):
    daily_data: list[DailyDataPoint]
    summary: WeeklySummary
    skill_scores: list[SkillScoreSchema]


class AnalyticsSummaryResponse(BaseModel):
    completion_rate: float
    practice_accuracy: float
    total_focus_minutes: int
    current_streak: int
    skills: list[SkillScoreSchema]
    weekly_history: list[WeeklySummary]
