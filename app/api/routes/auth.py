import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.models.gamification import Streak
from app.models.roadmap import Roadmap
from app.schemas.user import (
    SignupRequest, LoginRequest, TokenResponse,
    UserProfileSchema, UpdateProfileRequest, UserMeResponse,
)
from app.schemas.common import ApiResponse
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Supabase client cache (one instance per process) ─────────────────────────
_supabase_client = None

def _get_supabase():
    """Return a cached synchronous Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _supabase_client


async def _supabase_sign_up(email: str, password: str):
    """Run blocking Supabase sign_up in a thread so the event loop stays free."""
    def _call():
        sb = _get_supabase()
        return sb.auth.sign_up({"email": email, "password": password})
    return await asyncio.wait_for(asyncio.to_thread(_call), timeout=15)


async def _supabase_sign_in(email: str, password: str):
    """Run blocking Supabase sign_in_with_password in a thread."""
    def _call():
        sb = _get_supabase()
        return sb.auth.sign_in_with_password({"email": email, "password": password})
    return await asyncio.wait_for(asyncio.to_thread(_call), timeout=15)


async def _supabase_resend(email: str):
    """Run blocking Supabase resend in a thread."""
    def _call():
        sb = _get_supabase()
        return sb.auth.resend({"type": "signup", "email": email})
    return await asyncio.wait_for(asyncio.to_thread(_call), timeout=15)


class ResendConfirmationRequest(BaseModel):
    email: str


@router.post("/signup", response_model=ApiResponse[TokenResponse])
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user via Supabase and create local profile."""
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        return ApiResponse.fail("Email already registered")

    # Use Supabase auth if configured, else create local user
    supabase_uid = None
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        try:
            resp = await _supabase_sign_up(body.email, body.password)
            if resp.user:
                supabase_uid = resp.user.id
        except asyncio.TimeoutError:
            return ApiResponse.fail("Supabase signup timed out – please try again")
        except Exception as e:
            return ApiResponse.fail(f"Supabase signup failed: {str(e)}")
    else:
        # Dev mode: generate a local UID
        import uuid
        supabase_uid = str(uuid.uuid4())

    user = User(supabase_user_id=supabase_uid, email=body.email,
                hashed_password=hash_password(body.password))
    db.add(user)
    await db.flush()

    profile = UserProfile(user_id=user.id, name=body.name)
    db.add(profile)

    streak = Streak(user_id=user.id)
    db.add(streak)

    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": supabase_uid, "email": body.email})
    return ApiResponse.ok(TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
    ))


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login via Supabase credentials."""
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        try:
            resp = await _supabase_sign_in(body.email, body.password)
            if not resp.user:
                return ApiResponse.fail("Invalid credentials")
            supabase_uid = resp.user.id
        except asyncio.TimeoutError:
            return ApiResponse.fail("Login timed out – please try again")
        except Exception as e:
            err_str = str(e).lower()
            if "email not confirmed" in err_str or "email_not_confirmed" in err_str:
                return ApiResponse.fail(
                    "EMAIL_NOT_CONFIRMED: Please verify your email before signing in. "
                    "Check your inbox for a confirmation link."
                )
            if "invalid login credentials" in err_str or "invalid_credentials" in err_str:
                return ApiResponse.fail("Invalid email or password. Please try again.")
            return ApiResponse.fail(f"Login failed: {str(e)}")
    else:
        # Dev mode
        result = await db.execute(select(User).where(User.email == body.email))
        existing_user = result.scalar_one_or_none()
        if not existing_user:
            return ApiResponse.fail("User not found")
        if not existing_user.hashed_password or not verify_password(body.password, existing_user.hashed_password):
            return ApiResponse.fail("Invalid email or password")
        supabase_uid = existing_user.supabase_user_id

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        return ApiResponse.fail("User not found in local database")

    token = create_access_token({"sub": supabase_uid, "email": body.email})
    return ApiResponse.ok(TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
    ))


@router.post("/resend-confirmation", response_model=ApiResponse[dict])
async def resend_confirmation(body: ResendConfirmationRequest):
    """Resend Supabase email confirmation link."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_KEY):
        return ApiResponse.fail("Email confirmation not required in dev mode")
    try:
        await _supabase_resend(body.email)
        return ApiResponse.ok({"sent": True})
    except asyncio.TimeoutError:
        return ApiResponse.fail("Resend timed out – please try again")
    except Exception as e:
        return ApiResponse.fail(f"Could not resend: {str(e)}")


@router.get("/me", response_model=ApiResponse[UserMeResponse])
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get current authenticated user profile."""
    # Get profile
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()

    # Get streak
    streak_result = await db.execute(
        select(Streak).where(Streak.user_id == current_user.id)
    )
    streak = streak_result.scalar_one_or_none()
    streak_count = streak.streak_count if streak else 0

    # Get roadmap stats
    roadmap_result = await db.execute(
        select(Roadmap).where(Roadmap.user_id == current_user.id, Roadmap.is_active == True)
    )
    roadmap = roadmap_result.scalar_one_or_none()

    import json
    profile_schema = None
    if profile:
        skill_matrix = None
        if profile.skill_matrix:
            try:
                skill_matrix = {s["skill"]: s["score"] for s in json.loads(profile.skill_matrix)}
            except Exception:
                pass
        profile_schema = UserProfileSchema(
            id=profile.id,
            user_id=profile.user_id,
            name=profile.name,
            domain=profile.domain,
            level=profile.level,
            avatar_url=profile.avatar_url,
            joined_date=profile.joined_date,
            diagnosis_completed=profile.diagnosis_completed,
            skill_matrix=skill_matrix,
        )

    return ApiResponse.ok(UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        profile=profile_schema,
        streak_count=streak_count,
        total_completed=roadmap.completed_steps if roadmap else 0,
        total_steps=roadmap.total_steps if roadmap else 0,
    ))


@router.patch("/profile", response_model=ApiResponse[UserProfileSchema])
async def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    if body.name is not None:
        profile.name = body.name
    if body.domain is not None:
        profile.domain = body.domain
    if body.level is not None:
        profile.level = body.level
    if body.avatar_url is not None:
        profile.avatar_url = body.avatar_url

    await db.commit()
    await db.refresh(profile)

    return ApiResponse.ok(UserProfileSchema(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        domain=profile.domain,
        level=profile.level,
        avatar_url=profile.avatar_url,
        joined_date=profile.joined_date,
        diagnosis_completed=profile.diagnosis_completed,
    ))
