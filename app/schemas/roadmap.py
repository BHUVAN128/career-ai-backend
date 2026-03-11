from pydantic import BaseModel
from datetime import datetime


class ResourceLink(BaseModel):
    title: str
    url: str
    type: str = "article"  # article | video | docs | github


class StepSchema(BaseModel):
    id: str
    title: str
    description: str
    step_type: str
    status: str
    difficulty: str
    duration_minutes: int
    order_index: int
    content_data: dict | None = None
    resources: list[ResourceLink] = []

    class Config:
        from_attributes = True


class PhaseSchema(BaseModel):
    id: str
    title: str
    description: str
    order_index: int
    steps: list[StepSchema] = []

    class Config:
        from_attributes = True


class RoadmapSchema(BaseModel):
    id: str
    title: str
    domain: str
    level: str
    total_steps: int
    completed_steps: int
    phases: list[PhaseSchema] = []
    created_at: datetime

    class Config:
        from_attributes = True


class StepSubmitRequest(BaseModel):
    submission_type: str  # quiz | coding | reflection | project
    content: dict  # answers / code / text
    time_spent_seconds: int = 0


class StepSubmitResponse(BaseModel):
    score: float | None
    passed: bool
    feedback: dict
    next_step_id: str | None = None
    roadmap_adapted: bool = False


class UpdateStepStatusRequest(BaseModel):
    status: str  # active | completed


class GenerateRoadmapRequest(BaseModel):
    domain: str
    level: str
    skill_matrix: dict | None = None
