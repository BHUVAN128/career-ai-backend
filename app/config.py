from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Career AI API"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True

    # Database / Supabase
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    DATABASE_URL: str = ""

    # LLM
    LLM_PROVIDER: Literal["openai", "claude", "gemini", "groq"] = "groq"
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    LLM_MODEL: str = ""  # auto-selected per provider if empty
    LLM_MAX_OUTPUT_TOKENS: int = 700
    LLM_MAX_INPUT_CHARS: int = 12000

    # Security
    JWT_SECRET_KEY: str = "change-me-in-production"
    SUPABASE_JWT_SECRET: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # CORS
    FRONTEND_URL: str = "https://career-ai-frontend.vercel.app"
    ALLOWED_ORIGINS: list[str] = [
        "https://career-ai-frontend.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
