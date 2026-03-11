import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.services.llm.factory import get_llm_provider
from app.models.project import Project
from app.models.roadmap import Roadmap, Phase
from app.models.user import UserProfile
from app.schemas.gamification import ProjectSchema


PROJECT_SYSTEM_PROMPT = """You are an expert software engineering mentor who suggests practical GitHub portfolio projects.
Always respond with valid JSON only. Projects should be realistic and portfolio-worthy."""


def _fallback_projects(domain: str) -> list[dict]:
    d = domain or "Software Engineering"
    slug = d.lower().replace(" ", "-")
    return [
        {
            "title": f"{d} Starter Tracker",
            "description": f"Build a beginner-friendly {d} tracker app with clean architecture and testing.",
            "difficulty": "Beginner",
            "estimated_hours": 24,
            "skills_used": [d, "Git", "Testing", "API Integration"],
            "starter_repo_placeholder": f"{slug}-starter-tracker",
        },
        {
            "title": f"{d} Practice Platform",
            "description": f"Create an intermediate {d} practice platform with authentication, dashboard, and persistence.",
            "difficulty": "Intermediate",
            "estimated_hours": 42,
            "skills_used": [d, "Authentication", "Database", "Deployment"],
            "starter_repo_placeholder": f"{slug}-practice-platform",
        },
        {
            "title": f"{d} Capstone System",
            "description": f"Deliver an advanced end-to-end {d} capstone with observability, performance tuning, and CI/CD.",
            "difficulty": "Advanced",
            "estimated_hours": 64,
            "skills_used": [d, "System Design", "Observability", "Performance"],
            "starter_repo_placeholder": f"{slug}-capstone-system",
        },
    ]


def _project_to_schema(p: Project) -> ProjectSchema:
    return ProjectSchema(
        id=p.id,
        title=p.title,
        description=p.description,
        difficulty=p.difficulty,
        estimated_hours=p.estimated_hours,
        skills_used=json.loads(p.skills_used or "[]"),
        starter_repo_placeholder=p.starter_repo_placeholder,
        completed=p.completed,
        github_url=p.github_url,
    )


async def suggest_projects(db: AsyncSession, user_id: str) -> list[ProjectSchema]:
    """Generate live project suggestions from active roadmap domain and current weak topics."""
    roadmap_result = await db.execute(
        select(Roadmap)
        .where(Roadmap.user_id == user_id, Roadmap.is_active == True)
        .options(selectinload(Roadmap.phases).selectinload(Phase.steps))
    )
    roadmap = roadmap_result.scalar_one_or_none()

    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()

    domain = (roadmap.domain if roadmap and roadmap.domain else (profile.domain if profile and profile.domain else "Web Development"))
    level = (roadmap.level if roadmap and roadmap.level else (profile.level if profile and profile.level else "Beginner"))
    skill_matrix = json.loads(profile.skill_matrix or "[]") if profile else []

    completion_pct = 0
    if roadmap and roadmap.total_steps > 0:
        completion_pct = int((roadmap.completed_steps / roadmap.total_steps) * 100)

    weak_topics: list[str] = []
    if roadmap:
        for phase in sorted(roadmap.phases, key=lambda p: p.order_index):
            for step in sorted(phase.steps, key=lambda s: s.order_index):
                if step.status == "completed":
                    continue
                try:
                    content_data = json.loads(step.content_data or "{}")
                except Exception:
                    content_data = {}
                topic = content_data.get("topic_title") if isinstance(content_data, dict) else None
                if not isinstance(topic, str) or not topic.strip():
                    topic = step.title.split(" - ")[0]
                topic = topic.strip()
                if topic and topic not in weak_topics:
                    weak_topics.append(topic)
                if len(weak_topics) >= 6:
                    break
            if len(weak_topics) >= 6:
                break

    # Keep user's completed portfolio entries; refresh incomplete suggestions in real time.
    await db.execute(delete(Project).where(Project.user_id == user_id, Project.completed == False))
    await db.commit()

    llm = get_llm_provider()
    prompt = f"""Suggest the 3 best portfolio-worthy GitHub projects RIGHT NOW for a {level} {domain} learner.
The projects must align with the current roadmap domain and weak topics.

User Skills: {json.dumps(skill_matrix[:8])}
Roadmap Completion: {completion_pct}%
Weak topics to target: {json.dumps(weak_topics)}

Return JSON:
{{
  "projects": [
    {{
      "title": "Project title",
      "description": "Project description",
      "difficulty": "Beginner|Intermediate|Advanced",
      "estimated_hours": 20,
      "skills_used": ["skill1", "skill2"],
      "starter_repo_placeholder": "repo-name-starter"
    }}
  ]
}}

Rules:
- Exactly 3 projects.
- Must be domain-specific and portfolio-ready.
- Increase complexity from project 1 to 3.
- Include modern, real-world scope."""
    try:
        raw = await llm.generate_with_retry(PROJECT_SYSTEM_PROMPT, prompt)
    except Exception:
        raw = {"projects": _fallback_projects(domain)}

    projects_payload = raw.get("projects") if isinstance(raw, dict) else None
    if not isinstance(projects_payload, list) or not projects_payload:
        projects_payload = _fallback_projects(domain)

    fresh_projects: list[Project] = []
    for p_data in projects_payload[:3]:
        if not isinstance(p_data, dict):
            continue
        project = Project(
            user_id=user_id,
            title=str(p_data.get("title", "")).strip(),
            description=str(p_data.get("description", "")).strip(),
            difficulty=str(p_data.get("difficulty", "Beginner")).strip() or "Beginner",
            estimated_hours=int(p_data.get("estimated_hours", 24) or 24),
            skills_used=json.dumps(p_data.get("skills_used", [])),
            starter_repo_placeholder=p_data.get("starter_repo_placeholder"),
            completed=False,
        )
        db.add(project)
        fresh_projects.append(project)

    await db.commit()

    completed_result = await db.execute(
        select(Project).where(Project.user_id == user_id, Project.completed == True)
    )
    completed_projects = completed_result.scalars().all()
    ordered = fresh_projects + completed_projects
    return [_project_to_schema(p) for p in ordered]

