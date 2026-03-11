import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm.factory import get_llm_provider
from app.models.user import UserProfile
from app.schemas.diagnosis import DiagnosisResult, SkillMatrix, AssessmentQuestion, AssessmentQuestionsResponse


DIAGNOSIS_SYSTEM_PROMPT = """You are an expert career counselor and technical skill evaluator.
Your job is to analyze candidate information and produce structured skill assessments.
Always respond with valid JSON only. Be precise and honest in skill scoring."""


async def parse_resume(resume_text: str) -> DiagnosisResult:
    """Analyze resume text and produce a structured diagnosis."""
    llm = get_llm_provider()
    prompt = f"""Analyze this resume/profile and produce an HONEST structured skill assessment:

RESUME:
{resume_text[:3000]}

Return JSON with this exact structure:
{{
  "detected_level": "Beginner|Intermediate|Expert",
  "recommended_domain": "e.g. Web Development, Data Science, DevOps, Mobile Development",
  "skill_matrix": [
    {{"skill": "JavaScript", "score": 75}},
    ...all relevant skills with HONEST scores 0-100
  ],
  "summary": "2-3 sentence honest summary of the candidate's profile and experience level",
  "weaknesses": [
    "No experience with testing frameworks",
    "Limited cloud/deployment knowledge",
    "..."
  ],
  "available_domains": [
    "Web Development",
    "Backend Engineering",
    "..."
  ]
}}

Be HONEST. If the resume shows little experience, score skills low (10-30).
Do not inflate scores. weaknesses should be real, actionable gaps (3-5 items).
available_domains = all domains this person's skills partially cover (2-4 items)."""

    result = await llm.generate_with_retry(DIAGNOSIS_SYSTEM_PROMPT, prompt)
    skills = [SkillMatrix(**s) for s in result.get("skill_matrix", [])]
    return DiagnosisResult(
        detected_level=result.get("detected_level", "Beginner"),
        recommended_domain=result.get("recommended_domain", "Web Development"),
        skill_matrix=skills,
        summary=result.get("summary", ""),
        weaknesses=result.get("weaknesses", []),
        available_domains=result.get("available_domains", []),
    )


async def generate_assessment_questions(level: str, domain: str) -> AssessmentQuestionsResponse:
    """Generate adaptive 3-layer assessment questions."""
    llm = get_llm_provider()
    prompt = f"""Create an adaptive skill assessment for:
Level: {level}
Domain: {domain}

Generate exactly 9 questions - 3 per layer:
- Layer 1 (MCQ): Conceptual multiple-choice questions
- Layer 2 (Scenario): Situational scenario-based questions
- Layer 3 (Practical): Hands-on practical challenge description

Return JSON:
{{
  "questions": [
    {{
      "id": "q1",
      "question": "...",
      "type": "mcq",
      "options": ["A", "B", "C", "D"],
      "difficulty": "Beginner|Intermediate|Expert"
    }},
    {{
      "id": "q4",
      "question": "...",
      "type": "scenario",
      "options": null,
      "difficulty": "..."
    }},
    {{
      "id": "q7",
      "question": "...",
      "type": "practical",
      "options": null,
      "difficulty": "..."
    }}
  ]
}}"""

    result = await llm.generate_with_retry(DIAGNOSIS_SYSTEM_PROMPT, prompt)
    questions = [AssessmentQuestion(
        id=q.get("id", str(uuid.uuid4())),
        question=q["question"],
        type=q.get("type", "mcq"),
        options=q.get("options"),
        difficulty=q.get("difficulty", level),
    ) for q in result.get("questions", [])]

    return AssessmentQuestionsResponse(
        questions=questions,
        level=level,
        domain=domain,
        layer=1,
    )


async def evaluate_assessment(answers: list[dict], level: str, domain: str) -> DiagnosisResult:
    """Grade assessment and produce diagnosis result."""
    llm = get_llm_provider()
    prompt = f"""Evaluate these assessment answers for a {level} {domain} candidate:

Answers: {json.dumps(answers[:10])}

Based on the quality of answers, produce a skill assessment.
Return JSON:
{{
  "detected_level": "Beginner|Intermediate|Expert",
  "recommended_domain": "{domain}",
  "skill_matrix": [
    {{"skill": "Core {domain} Skills", "score": 70}},
    ...3-6 relevant skills with realistic scores
  ],
  "summary": "Brief assessment summary"
}}"""

    result = await llm.generate_with_retry(DIAGNOSIS_SYSTEM_PROMPT, prompt)
    skills = [SkillMatrix(**s) for s in result.get("skill_matrix", [])]
    return DiagnosisResult(
        detected_level=result.get("detected_level", level),
        recommended_domain=result.get("recommended_domain", domain),
        skill_matrix=skills,
        summary=result.get("summary", ""),
    )


async def save_diagnosis_to_profile(
    db: AsyncSession,
    user_id: str,
    diagnosis: DiagnosisResult,
):
    """Persist diagnosis results to the user profile."""
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()

    skill_matrix_json = json.dumps([s.dict() for s in diagnosis.skill_matrix])

    if profile:
        profile.level = diagnosis.detected_level
        profile.domain = diagnosis.recommended_domain
        profile.skill_matrix = skill_matrix_json
        profile.diagnosis_completed = True
    else:
        profile = UserProfile(
            user_id=user_id,
            level=diagnosis.detected_level,
            domain=diagnosis.recommended_domain,
            skill_matrix=skill_matrix_json,
            diagnosis_completed=True,
        )
        db.add(profile)

    await db.commit()
    return profile
