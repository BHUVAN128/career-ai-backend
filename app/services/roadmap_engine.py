import json
import re
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.roadmap import Phase, Roadmap, Step, StepSubmission
from app.services.llm.factory import get_llm_provider


ROADMAP_SYSTEM_PROMPT = """You are an expert curriculum designer for technical education.
Create practical, production-focused learning roadmaps.
Always respond with valid JSON only."""

STEP_TYPES_PER_TOPIC = ("reading", "quiz", "coding")
MIN_PHASES = 3
MAX_PHASES = 6
MIN_TOPICS_PER_PHASE = 4
MAX_TOPICS_PER_PHASE = 8
INITIAL_TOPICS_TO_GENERATE = 2
PREFETCH_TOPICS_PER_CLICK = 2


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "topic"


def _placeholder_content(topic_key: str, topic_title: str, step_type: str, topic_seq: int) -> dict:
    return {
        "is_placeholder": True,
        "topic_key": topic_key,
        "topic_title": topic_title,
        "topic_seq": topic_seq,
        "step_type": step_type,
    }


def _default_quiz_questions(topic: str) -> list[dict]:
    return [
        {
            "id": f"q{i}",
            "question": f"{topic}: question {i}",
            "options": ["A) Option A", "B) Option B", "C) Option C", "D) Option D"],
            "correct_answer": "A",
            "explanation": "Review the core concept and retry.",
        }
        for i in range(1, 6)
    ]


def _default_coding_challenges(topic: str) -> list[dict]:
    return [
        {
            "id": f"c{i}",
            "title": f"{topic} Challenge {i}",
            "problem": f"Implement a small {topic} task ({i}/5).",
            "starter_code": "# Write your solution here\n",
            "expected_output": "See challenge requirements",
            "hint": "Break the problem into small functions.",
        }
        for i in range(1, 6)
    ]


def _resource_bank(domain: str, topic: str) -> dict[str, list[dict]]:
    docs = [
        {"title": f"Official docs: {topic}", "url": "https://developer.mozilla.org/", "type": "docs"},
        {"title": f"{domain} reference guide", "url": "https://www.freecodecamp.org/learn/", "type": "docs"},
    ]
    quiz = [
        {"title": f"{topic} quiz practice", "url": "https://www.w3schools.com/quiztest/", "type": "quiz"},
    ]
    coding = [
        {"title": f"{topic} coding practice (LeetCode)", "url": "https://leetcode.com/problemset/", "type": "coding"},
        {"title": f"{topic} coding practice (HackerRank)", "url": "https://www.hackerrank.com/domains/tutorials/10-days-of-javascript", "type": "coding"},
    ]
    return {"docs": docs, "quiz": quiz, "coding": coding}


def _default_topic_payload(domain: str, level: str, topic_title: str) -> dict[str, Any]:
    resources = _resource_bank(domain, topic_title)
    return {
        "reading": {
            "description": f"Learn {topic_title} with practical examples and workflow tips.",
            "duration_minutes": 40,
            "key_concepts": [
                f"{topic_title} fundamentals",
                "core workflow",
                "common mistakes",
                "real-world usage",
            ],
            "learning_path": [
                f"Understand the concept of {topic_title}",
                "Study one realistic implementation",
                "Practice with a small hands-on exercise",
                "Review common failure cases and fixes",
                "Apply the concept in a mini workflow",
            ],
            "reading_material": (
                f"Step-by-step guide for {topic_title}:\n"
                "1. Read the basics and definitions.\n"
                "2. See how it fits in production workflows.\n"
                "3. Implement a small practical example.\n"
                "4. Debug common mistakes.\n"
                "5. Summarize what to remember."
            ),
            "video_search_query": f"{domain} {topic_title} tutorial {level}",
            "key_points": ["Concept explanation", "Hands-on demo", "Best practices"],
            "resources": resources["docs"],
        },
        "quiz": {
            "description": f"Test your understanding of {topic_title}.",
            "duration_minutes": 20,
            "questions": _default_quiz_questions(topic_title),
            "resources": resources["quiz"] + resources["docs"][:1],
        },
        "coding": {
            "description": f"Solve practical coding tasks for {topic_title}.",
            "duration_minutes": 50,
            "challenges": _default_coding_challenges(topic_title),
            "resources": resources["coding"] + resources["docs"][:1],
        },
    }


def _fallback_outline(domain: str, level: str) -> dict:
    del level
    phase_titles = ["Phase 1 - Foundation", "Phase 2 - Build Skills", "Phase 3 - Advanced Practice"]
    phases = []
    for p_idx, phase_title in enumerate(phase_titles):
        topics = [f"{domain} {phase_title.split('-')[-1].strip()} Topic {i}" for i in range(1, 7)]
        phases.append(
            {
                "title": phase_title,
                "description": f"{domain} roadmap for {phase_title.split('-')[-1].strip().lower()} stage.",
                "order_index": p_idx,
                "topics": topics,
            }
        )
    return {"title": f"{domain} Mastery Path", "phases": phases}


def _normalize_outline_payload(raw: dict, domain: str, level: str) -> dict:
    if not isinstance(raw, dict):
        return _fallback_outline(domain, level)
    phases = raw.get("phases")
    if not isinstance(phases, list) or not phases:
        return _fallback_outline(domain, level)

    normalized_phases = []
    for p_idx, phase_data in enumerate(phases[:MAX_PHASES]):
        if not isinstance(phase_data, dict):
            continue
        title = str(phase_data.get("title") or f"Phase {p_idx + 1}").strip()
        description = str(phase_data.get("description") or f"{title} learning sequence").strip()
        raw_topics = phase_data.get("topics", [])
        if not isinstance(raw_topics, list):
            raw_topics = []
        topics = [str(t).strip() for t in raw_topics if isinstance(t, str) and t.strip()]
        if len(topics) < MIN_TOPICS_PER_PHASE:
            for i in range(len(topics) + 1, MIN_TOPICS_PER_PHASE + 1):
                topics.append(f"{domain} {title} Topic {i}")
        normalized_phases.append(
            {
                "title": title,
                "description": description,
                "order_index": p_idx,
                "topics": topics[:MAX_TOPICS_PER_PHASE],
            }
        )
    if len(normalized_phases) < MIN_PHASES:
        fallback = _fallback_outline(domain, level)["phases"]
        normalized_phases.extend(fallback[len(normalized_phases):MIN_PHASES])
    return {
        "title": str(raw.get("title") or f"{domain} Mastery Path"),
        "phases": normalized_phases,
    }


def _topic_steps(topic_title: str) -> list[dict]:
    return [
        {
            "step_type": "reading",
            "title": f"{topic_title} - Learn",
            "description": f"Study the concepts and notes for {topic_title}.",
            "duration_minutes": 40,
        },
        {
            "step_type": "quiz",
            "title": f"{topic_title} - Quiz",
            "description": f"Check your understanding of {topic_title}.",
            "duration_minutes": 20,
        },
        {
            "step_type": "coding",
            "title": f"{topic_title} - Coding",
            "description": f"Practice coding problems for {topic_title}.",
            "duration_minutes": 50,
        },
    ]


def _parse_content_data(step: Step) -> dict:
    try:
        return json.loads(step.content_data or "{}")
    except Exception:
        return {}


def _infer_topic_title_from_step(step: Step) -> str:
    title = (step.title or "").strip()
    for suffix in (" - Learn", " - Quiz", " - Coding"):
        if title.endswith(suffix):
            return title[: -len(suffix)].strip() or title
    return title or "Topic"


def _collect_sorted_steps(roadmap: Roadmap) -> list[Step]:
    sorted_phases = sorted(roadmap.phases, key=lambda p: p.order_index)
    steps: list[Step] = []
    for phase in sorted_phases:
        steps.extend(sorted(phase.steps, key=lambda s: s.order_index))
    return steps


def _build_topic_groups(roadmap: Roadmap) -> list[dict]:
    groups: dict[str, dict] = {}
    encounter_order: list[str] = []
    next_seq = 0
    for step in _collect_sorted_steps(roadmap):
        cd = _parse_content_data(step)
        topic_key = cd.get("topic_key")
        topic_title = cd.get("topic_title")
        topic_seq = cd.get("topic_seq")
        if not isinstance(topic_key, str) or not topic_key.strip():
            continue
        if not isinstance(topic_title, str) or not topic_title.strip():
            topic_title = step.title.split(" - ")[0]
        if not isinstance(topic_seq, int):
            topic_seq = next_seq
            next_seq += 1

        if topic_key not in groups:
            groups[topic_key] = {
                "topic_key": topic_key,
                "topic_title": topic_title,
                "topic_seq": topic_seq,
                "steps": [],
            }
            encounter_order.append(topic_key)
        groups[topic_key]["steps"].append(step)

    ordered = [groups[k] for k in encounter_order]
    ordered.sort(key=lambda g: (g["topic_seq"], g["topic_key"]))
    for group in ordered:
        group["steps"] = sorted(group["steps"], key=lambda s: s.order_index)
    return ordered


async def _load_roadmap_for_step(db: AsyncSession, step_id: str) -> tuple[Step | None, Roadmap | None]:
    step_result = await db.execute(select(Step).where(Step.id == step_id))
    step = step_result.scalar_one_or_none()
    if not step:
        return None, None

    phase_result = await db.execute(select(Phase).where(Phase.id == step.phase_id))
    phase = phase_result.scalar_one_or_none()
    if not phase:
        return step, None

    roadmap_result = await db.execute(
        select(Roadmap)
        .where(Roadmap.id == phase.roadmap_id)
        .options(selectinload(Roadmap.phases).selectinload(Phase.steps))
    )
    roadmap = roadmap_result.scalar_one_or_none()
    return step, roadmap


async def _apply_topic_content(
    db: AsyncSession,
    roadmap: Roadmap,
    topic_key: str,
    force: bool = False,
) -> bool:
    groups = _build_topic_groups(roadmap)
    group = next((g for g in groups if g["topic_key"] == topic_key), None)
    if not group:
        return False
    related_steps: list[Step] = group["steps"]
    topic_title: str = group["topic_title"]

    if not force:
        all_ready = True
        for s in related_steps:
            cd = _parse_content_data(s)
            if cd.get("is_placeholder", True):
                all_ready = False
                break
        if all_ready:
            return False

    domain = roadmap.domain or "Software Engineering"
    level = roadmap.level or "Beginner"
    llm = get_llm_provider()
    prompt = f"""Create complete learning content for this topic.
Domain: {domain}
Level: {level}
Topic: {topic_title}

Return JSON ONLY:
{{
  "reading": {{
    "description": "...",
    "duration_minutes": 20-90,
    "key_concepts": ["..."],
    "learning_path": ["step 1", "step 2", "step 3", "step 4", "step 5"],
    "reading_material": "step-by-step written guide",
    "video_search_query": "...",
    "key_points": ["..."],
    "resources": [{{"title":"...", "url":"https://...", "type":"docs|video|reference"}}]
  }},
  "quiz": {{
    "description": "...",
    "duration_minutes": 10-45,
    "questions": [
      {{
        "id":"q1",
        "question":"...",
        "options":["A) ...","B) ...","C) ...","D) ..."],
        "correct_answer":"A",
        "explanation":"..."
      }}
    ],
    "resources": [{{"title":"...", "url":"https://...", "type":"quiz|docs"}}]
  }},
  "coding": {{
    "description": "...",
    "duration_minutes": 20-120,
    "challenges": [
      {{
        "id":"c1",
        "title":"...",
        "problem":"...",
        "starter_code":"...",
        "expected_output":"...",
        "hint":"..."
      }}
    ],
    "resources": [{{"title":"...", "url":"https://...", "type":"coding|docs"}}]
  }}
}}

Rules:
- Make the content domain-relevant and practical.
- reading must be step-by-step and detailed.
- quiz must contain exactly 5 MCQs.
- coding must contain 3 to 5 challenges.
- include useful external links for docs, quiz practice, and coding practice."""
    try:
        raw = await llm.generate_with_retry(ROADMAP_SYSTEM_PROMPT, prompt, max_output_tokens=2800)
    except Exception:
        raw = {}

    fallback = _default_topic_payload(domain, level, topic_title)
    reading_payload = raw.get("reading") if isinstance(raw, dict) else None
    quiz_payload = raw.get("quiz") if isinstance(raw, dict) else None
    coding_payload = raw.get("coding") if isinstance(raw, dict) else None
    if not isinstance(reading_payload, dict):
        reading_payload = fallback["reading"]
    if not isinstance(quiz_payload, dict):
        quiz_payload = fallback["quiz"]
    if not isinstance(coding_payload, dict):
        coding_payload = fallback["coding"]

    payload_map = {"reading": reading_payload, "quiz": quiz_payload, "coding": coding_payload}
    topic_seq = int(group["topic_seq"])
    for step in related_steps:
        payload = payload_map.get(step.step_type) or fallback.get(step.step_type) or {}
        if not isinstance(payload, dict):
            payload = {}
        if step.step_type == "reading" and not isinstance(payload.get("video_search_query"), str):
            payload["video_search_query"] = f"{domain} {topic_title} tutorial {level}"
        resources = payload.get("resources", [])
        if not isinstance(resources, list):
            resources = []

        content_data = {
            "is_placeholder": False,
            "topic_key": topic_key,
            "topic_title": topic_title,
            "topic_seq": topic_seq,
            **payload,
        }
        step.content_data = json.dumps(content_data)
        step.resources = json.dumps(resources)
        step.description = str(payload.get("description") or step.description)
        duration = payload.get("duration_minutes")
        if isinstance(duration, int):
            step.duration_minutes = max(10, min(180, duration))
    return True


def _roadmap_is_legacy(roadmap: Roadmap) -> bool:
    steps = _collect_sorted_steps(roadmap)
    if not steps:
        return False
    has_topic_key = False
    for step in steps:
        cd = _parse_content_data(step)
        if isinstance(cd.get("topic_key"), str):
            has_topic_key = True
        if step.step_type not in STEP_TYPES_PER_TOPIC:
            return True
    return not has_topic_key


def _ensure_progress_state(roadmap: Roadmap) -> bool:
    changed = False
    steps = [s for s in _collect_sorted_steps(roadmap) if s.status != "completed"]
    if not steps:
        return False
    active_steps = [s for s in steps if s.status == "active"]
    if not active_steps:
        first = steps[0]
        first.status = "active"
        changed = True
    elif len(active_steps) > 1:
        keep = active_steps[0]
        for step in active_steps[1:]:
            if step.id != keep.id:
                step.status = "locked"
                changed = True
    return changed


def _ensure_topic_metadata(roadmap: Roadmap) -> bool:
    changed = False
    steps = _collect_sorted_steps(roadmap)
    last_topic_title = None
    current_seq = -1
    for step in steps:
        cd = _parse_content_data(step)
        step_changed = False

        topic_title = cd.get("topic_title")
        topic_key = cd.get("topic_key")
        topic_seq = cd.get("topic_seq")

        if not isinstance(topic_title, str) or not topic_title.strip():
            topic_title = _infer_topic_title_from_step(step)
            cd["topic_title"] = topic_title
            step_changed = True
        else:
            topic_title = topic_title.strip()

        if topic_title != last_topic_title:
            current_seq += 1
            last_topic_title = topic_title

        if not isinstance(topic_seq, int):
            topic_seq = current_seq
            cd["topic_seq"] = topic_seq
            step_changed = True
        else:
            current_seq = topic_seq

        if not isinstance(topic_key, str) or not topic_key.strip():
            cd["topic_key"] = f"legacy-{topic_seq:03d}-{_slug(topic_title)[:40]}"
            step_changed = True

        if step.step_type == "reading" and not isinstance(cd.get("video_search_query"), str):
            cd["video_search_query"] = f"{roadmap.domain} {topic_title} tutorial {roadmap.level}"
            step_changed = True

        if step_changed:
            step.content_data = json.dumps(cd)
            changed = True
    return changed


async def generate_roadmap_outline(
    db: AsyncSession,
    user_id: str,
    domain: str,
    level: str,
    skill_matrix: dict | None = None,
) -> Roadmap:
    llm = get_llm_provider()
    skill_context = ""
    if skill_matrix:
        skill_context = f"\nCurrent skills: {json.dumps(skill_matrix)}"

    prompt = f"""Create only the outline for a personalized technical roadmap.
Domain: {domain}
Level: {level}
{skill_context}

Return JSON ONLY:
{{
  "title": "{domain} Mastery Path",
  "phases": [
    {{
      "title": "Phase title",
      "description": "...",
      "order_index": 0,
      "topics": ["Concrete topic 1", "Concrete topic 2", "..."]
    }}
  ]
}}

Rules:
- Number of phases should be based on the domain/level complexity (between {MIN_PHASES} and {MAX_PHASES}).
- Each phase should contain practical topics (between {MIN_TOPICS_PER_PHASE} and {MAX_TOPICS_PER_PHASE} topics).
- Topics must be progression-aware and useful.
- Do not use placeholders like "Fundamentals 1/2/3"."""
    try:
        raw = await llm.generate_with_retry(ROADMAP_SYSTEM_PROMPT, prompt, max_output_tokens=1800)
    except Exception:
        raw = _fallback_outline(domain, level)
    outline = _normalize_outline_payload(raw, domain, level)

    existing = await db.execute(select(Roadmap).where(Roadmap.user_id == user_id, Roadmap.is_active == True))
    for old in existing.scalars().all():
        old.is_active = False

    roadmap = Roadmap(
        user_id=user_id,
        title=outline.get("title", f"{domain} Mastery Path"),
        domain=domain,
        level=level,
        is_active=True,
    )
    db.add(roadmap)
    await db.flush()

    total_steps = 0
    topic_seq = 0
    for phase_data in outline.get("phases", []):
        phase = Phase(
            roadmap_id=roadmap.id,
            title=phase_data.get("title", ""),
            description=phase_data.get("description", ""),
            order_index=int(phase_data.get("order_index", 0)),
        )
        db.add(phase)
        await db.flush()

        topics = phase_data.get("topics", [])
        step_idx = 0
        for topic in topics:
            topic_title = str(topic).strip()
            topic_key = f"t{topic_seq:03d}-{_slug(topic_title)[:40]}"
            for step_blueprint in _topic_steps(topic_title):
                status = "locked"
                if topic_seq == 0 and step_blueprint["step_type"] == "reading":
                    status = "active"
                step = Step(
                    phase_id=phase.id,
                    title=step_blueprint["title"],
                    description=step_blueprint["description"],
                    step_type=step_blueprint["step_type"],
                    status=status,
                    difficulty=level,
                    duration_minutes=step_blueprint["duration_minutes"],
                    order_index=step_idx,
                    content_data=json.dumps(
                        _placeholder_content(
                            topic_key=topic_key,
                            topic_title=topic_title,
                            step_type=step_blueprint["step_type"],
                            topic_seq=topic_seq,
                        )
                    ),
                    resources=json.dumps([]),
                )
                db.add(step)
                step_idx += 1
                total_steps += 1
            topic_seq += 1

    roadmap.total_steps = total_steps
    await db.commit()
    result = await db.execute(
        select(Roadmap)
        .where(Roadmap.id == roadmap.id)
        .options(selectinload(Roadmap.phases).selectinload(Phase.steps))
    )
    return result.scalar_one()


async def _generate_initial_topics(db: AsyncSession, roadmap: Roadmap, count: int) -> list[str]:
    generated: list[str] = []
    groups = _build_topic_groups(roadmap)
    for group in groups[:count]:
        if await _apply_topic_content(db, roadmap, group["topic_key"]):
            generated.append(group["topic_key"])
    if generated:
        await db.commit()
    return generated


async def generate_topic_batch_from_step(
    db: AsyncSession,
    user_id: str,
    step_id: str,
    prefetch_topics: int = PREFETCH_TOPICS_PER_CLICK,
) -> dict:
    step, roadmap = await _load_roadmap_for_step(db, step_id)
    if not step:
        return {"generated": False, "reason": "step_not_found"}
    if not roadmap:
        return {"generated": False, "reason": "roadmap_not_found"}
    if roadmap.user_id != user_id:
        return {"generated": False, "reason": "forbidden"}

    clicked_cd = _parse_content_data(step)
    clicked_key = clicked_cd.get("topic_key")
    if not isinstance(clicked_key, str) or not clicked_key.strip():
        return {"generated": False, "reason": "topic_key_missing"}

    groups = _build_topic_groups(roadmap)
    idx = next((i for i, g in enumerate(groups) if g["topic_key"] == clicked_key), -1)
    if idx < 0:
        return {"generated": False, "reason": "topic_not_found"}

    generated_keys: list[str] = []
    if await _apply_topic_content(db, roadmap, clicked_key):
        generated_keys.append(clicked_key)

    prefetch_keys: list[str] = []
    for group in groups[idx + 1: idx + 1 + max(0, prefetch_topics)]:
        topic_key = group["topic_key"]
        prefetch_keys.append(topic_key)
        if await _apply_topic_content(db, roadmap, topic_key):
            generated_keys.append(topic_key)

    if generated_keys:
        await db.commit()

    return {
        "generated": True,
        "clicked_topic_key": clicked_key,
        "generated_topic_keys": generated_keys,
        "prefetch_topic_keys": prefetch_keys,
    }


async def generate_roadmap(
    db: AsyncSession,
    user_id: str,
    domain: str,
    level: str,
    skill_matrix: dict | None = None,
) -> Roadmap:
    """Generate outline first, then eagerly generate first two topics."""
    roadmap = await generate_roadmap_outline(
        db=db,
        user_id=user_id,
        domain=domain,
        level=level,
        skill_matrix=skill_matrix,
    )
    await _generate_initial_topics(db, roadmap, INITIAL_TOPICS_TO_GENERATE)
    refreshed = await db.execute(
        select(Roadmap)
        .where(Roadmap.id == roadmap.id)
        .options(selectinload(Roadmap.phases).selectinload(Phase.steps))
    )
    return refreshed.scalar_one()


async def get_user_roadmap(db: AsyncSession, user_id: str) -> Roadmap | None:
    """Get user's active roadmap and self-heal duplicates + legacy roadmap format."""
    result = await db.execute(
        select(Roadmap)
        .where(Roadmap.user_id == user_id, Roadmap.is_active == True)
        .order_by(desc(Roadmap.updated_at), desc(Roadmap.created_at))
        .options(selectinload(Roadmap.phases).selectinload(Phase.steps))
    )
    active_roadmaps = result.scalars().all()
    if not active_roadmaps:
        return None

    roadmap = active_roadmaps[0]
    changed = False
    for duplicate in active_roadmaps[1:]:
        if duplicate.is_active:
            duplicate.is_active = False
            changed = True

    if _roadmap_is_legacy(roadmap):
        try:
            return await generate_roadmap(
                db=db,
                user_id=user_id,
                domain=roadmap.domain or "Software Engineering",
                level=roadmap.level or "Beginner",
                skill_matrix=None,
            )
        except Exception:
            # Keep serving existing roadmap if regeneration fails.
            pass

    if _ensure_topic_metadata(roadmap):
        changed = True

    if _ensure_progress_state(roadmap):
        changed = True

    if changed:
        await db.commit()
    return roadmap


async def complete_step_and_unlock_next(
    db: AsyncSession,
    user_id: str,
    step_id: str,
    score: float,
) -> dict:
    """Mark step complete, unlock next, and adapt if needed."""
    result = await db.execute(select(Step).where(Step.id == step_id))
    step = result.scalar_one_or_none()
    if not step:
        return {"adapted": False, "next_step_id": None}

    step.status = "completed"

    phase_result = await db.execute(select(Phase).where(Phase.id == step.phase_id))
    phase = phase_result.scalar_one_or_none()

    next_step_id = None
    adapted = False

    if phase:
        next_step_result = await db.execute(
            select(Step).where(Step.phase_id == phase.id, Step.order_index == step.order_index + 1)
        )
        next_step = next_step_result.scalar_one_or_none()

        if not next_step:
            roadmap_result = await db.execute(select(Roadmap).where(Roadmap.id == phase.roadmap_id))
            roadmap = roadmap_result.scalar_one_or_none()
            if roadmap:
                next_phase_result = await db.execute(
                    select(Phase)
                    .where(Phase.roadmap_id == roadmap.id, Phase.order_index == phase.order_index + 1)
                    .options(selectinload(Phase.steps))
                )
                next_phase = next_phase_result.scalar_one_or_none()
                if next_phase and next_phase.steps:
                    next_step = next_phase.steps[0]

        if next_step:
            next_step.status = "active"
            next_step_id = next_step.id

        roadmap_result = await db.execute(select(Roadmap).where(Roadmap.id == phase.roadmap_id))
        roadmap = roadmap_result.scalar_one_or_none()
        if roadmap:
            roadmap.completed_steps = roadmap.completed_steps + 1

        existing_submissions = await db.execute(
            select(StepSubmission).where(
                StepSubmission.step_id == step_id, StepSubmission.user_id == user_id
            )
        )
        attempts = len(existing_submissions.scalars().all())
        if score < 50 and attempts >= 2:
            adapted = await _insert_reinforcement_module(db, phase, step)

    await db.commit()
    return {"adapted": adapted, "next_step_id": next_step_id}


async def _insert_reinforcement_module(db: AsyncSession, phase: Phase, failed_step: Step) -> bool:
    """Insert a review step before the failed step if not already present."""
    review_result = await db.execute(
        select(Step).where(
            Step.phase_id == phase.id,
            Step.title.like("Review:%"),
            Step.order_index == failed_step.order_index - 1,
        )
    )
    if review_result.scalar_one_or_none():
        return False

    steps_to_shift = await db.execute(
        select(Step).where(Step.phase_id == phase.id, Step.order_index >= failed_step.order_index)
    )
    for s in steps_to_shift.scalars().all():
        s.order_index += 1

    review_step = Step(
        phase_id=phase.id,
        title=f"Review: {failed_step.title}",
        description=f"Let's reinforce the concepts from '{failed_step.title}' before moving on.",
        step_type="reading",
        status="active",
        difficulty="Beginner",
        duration_minutes=20,
        order_index=failed_step.order_index - 1,
        content_data=json.dumps(
            {
                "key_concepts": ["Review of core concepts"],
                "reading_material": f"This is a review session for {failed_step.title}. Focus on fundamentals before proceeding.",
            }
        ),
        resources=failed_step.resources,
    )
    db.add(review_step)
    return True
