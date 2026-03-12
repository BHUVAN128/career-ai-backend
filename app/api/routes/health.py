from fastapi import APIRouter
from datetime import datetime, timezone
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
    }
@router.head("/health")
async def health_head():
    return


@router.get("/ready")
async def readiness_check():
    """Check if all dependencies are available."""
    # Read directly from .env to get the real current config
    import os
    from pathlib import Path
    env_path = Path(__file__).resolve().parents[3] / ".env"
    env_vars: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()

    def key(k: str) -> str:
        return env_vars.get(k) or os.environ.get(k, "")

    llm_configured = bool(
        key("GROQ_API_KEY") or key("OPENAI_API_KEY")
        or key("ANTHROPIC_API_KEY") or key("GOOGLE_API_KEY")
    )
    active_provider = key("LLM_PROVIDER") or settings.LLM_PROVIDER
    checks = {
        "api": True,
        "llm_configured": llm_configured,
        "active_provider": active_provider,
    }
    all_ready = checks["api"] and checks["llm_configured"]
    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
