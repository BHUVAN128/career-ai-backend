import uuid
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm.factory import get_llm_provider
from app.models.project import MockInterview
from app.schemas.gamification import (
    InterviewStartResponse, InterviewAnswerResponse,
    InterviewResultResponse, InterviewQuestionSchema,
)


INTERVIEW_SYSTEM_PROMPT = """You are conducting a professional technical interview.
Ask relevant, thoughtful questions and evaluate responses with expert-level insight.
Always respond with valid JSON only."""


async def start_interview(db: AsyncSession, user_id: str, domain: str, level: str) -> InterviewStartResponse:
    """Begin a new mock interview session."""
    llm = get_llm_provider()
    prompt = f"""Generate 6 interview questions for a {level} {domain} position.
Mix: 2 behavioral, 2 technical, 2 situational.

Return JSON:
{{
  "questions": [
    {{
      "id": "q1",
      "question": "Tell me about a challenging technical project you worked on.",
      "type": "behavioral"
    }},
    {{
      "id": "q2",
      "question": "Explain the difference between synchronous and asynchronous programming.",
      "type": "technical"
    }},
    ...4 more questions
  ]
}}"""

    result = await llm.generate_with_retry(INTERVIEW_SYSTEM_PROMPT, prompt)
    questions = result.get("questions", [])
    if not questions:
        questions = [{"id": "q1", "question": f"Tell me about your experience with {domain}.", "type": "behavioral"}]

    interview = MockInterview(
        user_id=user_id,
        domain=domain,
        level=level,
        questions=json.dumps(questions),
        current_question_index=0,
        status="in_progress",
        transcript="[]",
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)

    first_q = questions[0]
    return InterviewStartResponse(
        interview_id=interview.id,
        question=InterviewQuestionSchema(
            id=first_q.get("id", "q1"),
            question=first_q.get("question", ""),
            type=first_q.get("type", "behavioral"),
        ),
        question_number=1,
        total_questions=len(questions),
    )


async def process_answer(
    db: AsyncSession,
    interview_id: str,
    user_id: str,
    answer: str,
) -> InterviewAnswerResponse:
    """Record answer and return next question."""
    result = await db.execute(
        select(MockInterview)
        .where(MockInterview.id == interview_id, MockInterview.user_id == user_id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise ValueError("Interview not found")

    questions = json.loads(interview.questions)
    transcript = json.loads(interview.transcript)
    current_q = questions[interview.current_question_index]

    # Append to transcript
    transcript.append({
        "question": current_q.get("question", ""),
        "answer": answer,
        "question_type": current_q.get("type", ""),
    })

    interview.transcript = json.dumps(transcript)
    interview.current_question_index += 1
    next_index = interview.current_question_index
    total = len(questions)

    if next_index >= total:
        # All questions answered — finalize
        interview.status = "completed"
        interview.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return InterviewAnswerResponse(
            acknowledged=True,
            next_question=None,
            question_number=total,
            total_questions=total,
            completed=True,
        )

    next_q = questions[next_index]
    await db.commit()
    return InterviewAnswerResponse(
        acknowledged=True,
        next_question=InterviewQuestionSchema(
            id=next_q.get("id", ""),
            question=next_q.get("question", ""),
            type=next_q.get("type", "behavioral"),
        ),
        question_number=next_index + 1,
        total_questions=total,
        completed=False,
    )


async def get_interview_result(
    db: AsyncSession,
    interview_id: str,
    user_id: str,
) -> InterviewResultResponse:
    """Score the completed interview."""
    result = await db.execute(
        select(MockInterview)
        .where(MockInterview.id == interview_id, MockInterview.user_id == user_id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise ValueError("Interview not found")

    # Return cached scores if already evaluated
    if interview.overall_score is not None:
        return InterviewResultResponse(
            interview_id=interview.id,
            technical_score=interview.technical_score or 0,
            clarity_score=interview.clarity_score or 0,
            confidence_score=interview.confidence_score or 0,
            completeness_score=interview.completeness_score or 0,
            overall_score=interview.overall_score or 0,
            feedback=interview.final_feedback or "Interview completed.",
            transcript=json.loads(interview.transcript or "[]"),
        )

    transcript = json.loads(interview.transcript or "[]")
    llm = get_llm_provider()
    prompt = f"""Score this {interview.level} {interview.domain} interview transcript:

TRANSCRIPT:
{json.dumps(transcript[:6])}

Rate each dimension from 0-10 and provide brief feedback.
Return JSON:
{{
  "technical_score": 7.5,
  "clarity_score": 8.0,
  "confidence_score": 7.0,
  "completeness_score": 7.5,
  "overall_score": 7.5,
  "feedback": "Overall strong performance. Technical understanding is solid..."
}}"""

    scores = await llm.generate_with_retry(INTERVIEW_SYSTEM_PROMPT, prompt)

    interview.technical_score = float(scores.get("technical_score", 7))
    interview.clarity_score = float(scores.get("clarity_score", 7))
    interview.confidence_score = float(scores.get("confidence_score", 7))
    interview.completeness_score = float(scores.get("completeness_score", 7))
    interview.overall_score = float(scores.get("overall_score", 7))
    interview.final_feedback = scores.get("feedback", "Interview completed.")
    await db.commit()

    return InterviewResultResponse(
        interview_id=interview.id,
        technical_score=interview.technical_score,
        clarity_score=interview.clarity_score,
        confidence_score=interview.confidence_score,
        completeness_score=interview.completeness_score,
        overall_score=interview.overall_score,
        feedback=interview.final_feedback,
        transcript=transcript,
    )
