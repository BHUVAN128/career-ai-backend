from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.database import init_db
from app.core.exceptions import CareerAIException
from app.middleware.logging import LoggingMiddleware
from app.middleware.error_handler import career_ai_exception_handler, generic_exception_handler
from app.api.routes import auth, diagnosis, roadmap, chat, analytics, gamification, interview, health, internships


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB tables on startup."""
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Career AI — Adaptive Learning Platform API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(LoggingMiddleware)

# ─── Exception Handlers ───────────────────────────────────────────────────────

app.add_exception_handler(CareerAIException, career_ai_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# ─── Routes ───────────────────────────────────────────────────────────────────

API_PREFIX = "/api"

app.include_router(health.router)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(diagnosis.router, prefix=API_PREFIX)
app.include_router(roadmap.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(gamification.router, prefix=API_PREFIX)
app.include_router(interview.router, prefix=API_PREFIX)
app.include_router(internships.router, prefix=API_PREFIX)
