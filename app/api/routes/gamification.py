import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.gamification import Badge, UserBadge, Streak
from app.models.project import Project, Internship
from app.schemas.gamification import (
    BadgeSchema, StreakSchema, ProjectSchema,
    SubmitProjectRequest, InternshipSchema,
)
from app.schemas.common import ApiResponse
from app.services import streak_engine, project_engine

router = APIRouter(prefix="/gamification", tags=["gamification"])


# ─── Streak ───────────────────────────────────────────────────────────────────

@router.get("/streak", response_model=ApiResponse[StreakSchema])
async def get_streak(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await streak_engine.get_streak_status(db, current_user.id)
    return ApiResponse.ok(data)


# ─── Badges ───────────────────────────────────────────────────────────────────

@router.get("/badges", response_model=ApiResponse[list[BadgeSchema]])
async def get_badges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all badges with unlock status for the current user."""
    # Get all badges
    all_badges_result = await db.execute(select(Badge))
    all_badges = all_badges_result.scalars().all()

    # Get user's unlocked badges
    user_badges_result = await db.execute(
        select(UserBadge).where(UserBadge.user_id == current_user.id)
    )
    user_badges = {ub.badge_id: ub for ub in user_badges_result.scalars().all()}

    badge_schemas = []
    for badge in all_badges:
        ub = user_badges.get(badge.id)
        badge_schemas.append(BadgeSchema(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
            unlocked=ub.unlocked if ub else False,
            unlocked_at=ub.unlocked_at if ub else None,
        ))

    return ApiResponse.ok(badge_schemas)


@router.post("/badges/check", response_model=ApiResponse[list[str]])
async def check_badges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate and unlock earned badges. Returns list of newly unlocked badge names."""
    from app.models.roadmap import Roadmap
    from datetime import datetime, timezone

    roadmap_result = await db.execute(
        select(Roadmap).where(Roadmap.user_id == current_user.id, Roadmap.is_active == True)
    )
    roadmap = roadmap_result.scalar_one_or_none()
    completed_steps = roadmap.completed_steps if roadmap else 0

    streak_result = await db.execute(select(Streak).where(Streak.user_id == current_user.id))
    streak = streak_result.scalar_one_or_none()
    streak_count = streak.streak_count if streak else 0

    badges_result = await db.execute(select(Badge))
    all_badges = badges_result.scalars().all()

    newly_unlocked = []
    for badge in all_badges:
        # Check if already unlocked
        ub_result = await db.execute(
            select(UserBadge).where(
                UserBadge.user_id == current_user.id,
                UserBadge.badge_id == badge.id,
            )
        )
        ub = ub_result.scalar_one_or_none()
        if ub and ub.unlocked:
            continue

        # Check condition
        earned = False
        if badge.condition_type == "steps_completed" and completed_steps >= badge.condition_value:
            earned = True
        elif badge.condition_type == "streak" and streak_count >= badge.condition_value:
            earned = True

        if earned:
            if ub:
                ub.unlocked = True
                ub.unlocked_at = datetime.now(timezone.utc)
            else:
                db.add(UserBadge(
                    user_id=current_user.id,
                    badge_id=badge.id,
                    unlocked=True,
                    unlocked_at=datetime.now(timezone.utc),
                ))
            newly_unlocked.append(badge.name)

    await db.commit()
    return ApiResponse.ok(newly_unlocked)


# ─── Projects ─────────────────────────────────────────────────────────────────

@router.get("/projects", response_model=ApiResponse[list[ProjectSchema]])
async def get_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get personalized project suggestions."""
    projects = await project_engine.suggest_projects(db, current_user.id)
    return ApiResponse.ok(projects)


@router.post("/projects/submit", response_model=ApiResponse[ProjectSchema])
async def submit_project(
    body: SubmitProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a project as completed."""
    from datetime import datetime, timezone
    result = await db.execute(
        select(Project).where(
            Project.id == body.project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return ApiResponse.fail("Project not found")

    project.completed = True
    project.github_url = body.github_url
    project.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)

    return ApiResponse.ok(ProjectSchema(
        id=project.id,
        title=project.title,
        description=project.description,
        difficulty=project.difficulty,
        estimated_hours=project.estimated_hours,
        skills_used=json.loads(project.skills_used or "[]"),
        starter_repo_placeholder=project.starter_repo_placeholder,
        completed=project.completed,
        github_url=project.github_url,
    ))


# ─── Internships ──────────────────────────────────────────────────────────────

@router.get("/internships", response_model=ApiResponse[list[InternshipSchema]])
async def get_internships(
    domain: str | None = None,
    level: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get internship listings filtered by domain and level."""
    query = select(Internship).where(Internship.is_active == True)
    if domain:
        query = query.where(Internship.domain.ilike(f"%{domain}%"))
    if level:
        query = query.where(Internship.level == level)

    result = await db.execute(query.limit(20))
    internships = result.scalars().all()

    return ApiResponse.ok([
        InternshipSchema(
            id=i.id,
            title=i.title,
            company=i.company,
            domain=i.domain,
            location=i.location,
            level=i.level,
            description=i.description,
            required_skills=json.loads(i.required_skills or "[]"),
            apply_url=i.apply_url,
        )
        for i in internships
    ])
