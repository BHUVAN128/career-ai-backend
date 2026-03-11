from pydantic import BaseModel, EmailStr
from datetime import datetime


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class UserProfileSchema(BaseModel):
    id: str
    user_id: str
    name: str
    domain: str
    level: str
    avatar_url: str | None
    joined_date: datetime
    diagnosis_completed: bool
    skill_matrix: dict | None = None

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    domain: str | None = None
    level: str | None = None
    avatar_url: str | None = None


class UserMeResponse(BaseModel):
    id: str
    email: str
    profile: UserProfileSchema | None
    streak_count: int = 0
    total_completed: int = 0
    total_steps: int = 0
