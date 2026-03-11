import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.roadmap import Roadmap, Phase, Step
from app.models.analytics import SkillScore
from app.schemas.roadmap import (
    RoadmapSchema, PhaseSchema, StepSchema,
    StepSubmitRequest, StepSubmitResponse,
    GenerateRoadmapRequest, ResourceLink,
)
from app.schemas.common import ApiResponse
from app.services import roadmap_engine, evaluation, analytics_engine, streak_engine
from app.services import video_service

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


def _step_to_schema(step: Step) -> StepSchema:
    resources = []
    try:
        raw = json.loads(step.resources or "[]")
        resources = [ResourceLink(**r) for r in raw if isinstance(r, dict)]
    except Exception:
        pass

    content_data = None
    try:
        content_data = json.loads(step.content_data or "{}") or None
    except Exception:
        pass

    return StepSchema(
        id=step.id,
        title=step.title,
        description=step.description,
        step_type=step.step_type,
        status=step.status,
        difficulty=step.difficulty,
        duration_minutes=step.duration_minutes,
        order_index=step.order_index,
        content_data=content_data,
        resources=resources,
    )


def _roadmap_to_schema(roadmap: Roadmap) -> RoadmapSchema:
    phases = []
    for phase in sorted(roadmap.phases, key=lambda p: p.order_index):
        steps = [_step_to_schema(s) for s in sorted(phase.steps, key=lambda s: s.order_index)]
        phases.append(PhaseSchema(
            id=phase.id,
            title=phase.title,
            description=phase.description,
            order_index=phase.order_index,
            steps=steps,
        ))
    return RoadmapSchema(
        id=roadmap.id,
        title=roadmap.title,
        domain=roadmap.domain,
        level=roadmap.level,
        total_steps=roadmap.total_steps,
        completed_steps=roadmap.completed_steps,
        phases=phases,
        created_at=roadmap.created_at,
    )


@router.get("", response_model=ApiResponse[RoadmapSchema])
async def get_roadmap(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's active personalized roadmap."""
    roadmap = await roadmap_engine.get_user_roadmap(db, current_user.id)
    if not roadmap:
        return ApiResponse.fail("No roadmap found. Complete diagnosis first.")
    return ApiResponse.ok(_roadmap_to_schema(roadmap))


@router.post("/generate", response_model=ApiResponse[RoadmapSchema])
async def generate_roadmap(
    body: GenerateRoadmapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger roadmap generation."""
    from app.core.exceptions import LLMError
    try:
        roadmap = await roadmap_engine.generate_roadmap(
            db=db,
            user_id=current_user.id,
            domain=body.domain,
            level=body.level,
            skill_matrix=body.skill_matrix,
        )
        return ApiResponse.ok(_roadmap_to_schema(roadmap))
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"Failed to generate roadmap: {str(exc)[:200]}") from exc


@router.get("/step/{step_id}/video")
async def get_step_video(
    step_id: str,
    lang: str = Query(default="en", max_length=10),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the best YouTube video for a roadmap step in the requested language."""
    result = await db.execute(select(Step).where(Step.id == step_id))
    step = result.scalar_one_or_none()
    if not step:
        return ApiResponse.fail("Step not found")

    content_data = {}
    try:
        content_data = json.loads(step.content_data or "{}")
    except Exception:
        pass

    query = (
        content_data.get("video_search_query")
        or content_data.get("search_query")
        or step.title
    )

    video = await video_service.get_best_video(step_id, query, lang)
    if not video:
        return ApiResponse.ok({"found": False, "query": query})
    return ApiResponse.ok({"found": True, **video})


@router.get("/step/{step_id}", response_model=ApiResponse[StepSchema])
async def get_step(
    step_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed content for a specific step."""
    result = await db.execute(select(Step).where(Step.id == step_id))
    step = result.scalar_one_or_none()
    if not step:
        return ApiResponse.fail("Step not found")
    return ApiResponse.ok(_step_to_schema(step))


@router.post("/topic/{step_id}/generate-content")
async def generate_topic_content(
    step_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate clicked topic content and prefetch next topic pair."""
    result = await roadmap_engine.generate_topic_batch_from_step(
        db=db,
        user_id=current_user.id,
        step_id=step_id,
    )
    if result.get("reason") == "step_not_found":
        return ApiResponse.fail("Step not found")
    if result.get("reason") == "forbidden":
        return ApiResponse.fail("Not authorized for this topic")
    return ApiResponse.ok(result)


@router.post("/step/{step_id}/submit", response_model=ApiResponse[StepSubmitResponse])
async def submit_step(
    step_id: str,
    body: StepSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit work for a step and receive AI-generated feedback."""
    result = await db.execute(select(Step).where(Step.id == step_id))
    step = result.scalar_one_or_none()
    if not step:
        return ApiResponse.fail("Step not found")

    try:
        content_data = json.loads(step.content_data or "{}")
    except Exception:
        content_data = {}
    if bool(content_data.get("is_placeholder")):
        return ApiResponse.fail("Topic content is still being generated. Open the topic and try again.")

    # Evaluate based on submission type
    eval_result = {}
    if body.submission_type == "quiz":
        # accepts dict {q_id: answer} or list [{question_id, answer}]
        answers = body.content.get("answers") or body.content
        eval_result = await evaluation.evaluate_quiz(answers, step)
    elif body.submission_type == "coding":
        # accept {challenges: {c_id: code}} for multi-challenge, or legacy {code: str}
        code_data = body.content.get("challenges") or body.content.get("code", "")
        eval_result = await evaluation.evaluate_code(code_data, step)
    else:  # reflection, project, theory
        text = body.content.get("text", "") or str(body.content)
        eval_result = await evaluation.evaluate_theory(text, step)

    score = float(eval_result.get("score", 0))
    passed = bool(eval_result.get("passed", score >= 70))
    feedback = eval_result.get("feedback", {})

    # Log submission
    await evaluation.log_submission(
        db=db,
        step_id=step_id,
        user_id=current_user.id,
        submission_type=body.submission_type,
        content=body.content,
        score=score,
        passed=passed,
        feedback=feedback,
        time_spent_seconds=body.time_spent_seconds,
    )

    # If passed, complete step and unlock next
    next_step_id = None
    adapted = False
    if passed:
        result_data = await roadmap_engine.complete_step_and_unlock_next(
            db=db, user_id=current_user.id, step_id=step_id, score=score,
        )
        next_step_id = result_data.get("next_step_id")
        adapted = result_data.get("adapted", False)

        # Update analytics & streak
        await analytics_engine.log_activity(
            db=db, user_id=current_user.id,
            steps_completed=1,
            time_spent_minutes=body.time_spent_seconds // 60,
            quiz_accuracy=score if body.submission_type in ("quiz", "coding") else None,
        )
        await streak_engine.update_streak(db, current_user.id)

        # Update skill scores from ACTUAL quiz/coding performance (honest scores)
        if body.submission_type in ("quiz", "coding"):
            # Get the domain from user's active roadmap for skill labeling
            roadmap_res = await db.execute(
                select(Roadmap).where(
                    Roadmap.user_id == current_user.id,
                    Roadmap.is_active == True,
                ).order_by(desc(Roadmap.updated_at), desc(Roadmap.created_at))
            )
            active_roadmap = roadmap_res.scalars().first()
            if active_roadmap:
                skill_label = f"{active_roadmap.domain} – {step.step_type.capitalize()}"
                # Weighted average with any existing score
                existing_skill = await db.execute(
                    select(SkillScore)
                    .where(SkillScore.user_id == current_user.id, SkillScore.skill == skill_label)
                )
                existing = existing_skill.scalar_one_or_none()
                new_score = score if not existing else round((existing.score + score) / 2, 1)
                await analytics_engine.update_skill_scores(
                    db, current_user.id, {skill_label: new_score}
                )

    return ApiResponse.ok(StepSubmitResponse(
        score=score,
        passed=passed,
        feedback=feedback,
        next_step_id=next_step_id,
        roadmap_adapted=adapted,
    ))
