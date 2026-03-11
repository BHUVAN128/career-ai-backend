from pydantic import BaseModel
from typing import List, Optional


class InternshipRecommendation(BaseModel):
    platform: str
    title: str
    description: str
    apply_url: str
    skills_needed: List[str]
    duration: str
    stipend_range: Optional[str] = None
    location: str


class InternshipsResponse(BaseModel):
    eligible: bool
    domain: str
    level: str
    completion_percent: float
    recommendations: List[InternshipRecommendation]
    message: Optional[str] = None
