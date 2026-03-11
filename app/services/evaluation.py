"""
Evaluation engine: grades quiz answers and code submissions.
- Quiz:   auto-grades per-question MCQs against stored correct_answer keys.
- Coding: LLM evaluates each submitted challenge and returns per-challenge feedback.
- Theory: LLM rubric evaluation for reflections / project write-ups.
"""
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm.factory import get_llm_provider
from app.models.roadmap import Step, StepSubmission


EVAL_SYSTEM_PROMPT = """You are an expert technical evaluator.
Grade submissions fairly and provide constructive, detailed feedback.
Always respond with valid JSON only."""


async def evaluate_quiz(answers, step: Step) -> dict:
    """
    Auto-grade MCQ quiz answers.
    answers can be:
      - List[{question_id, answer}]        (legacy)
      - Dict[question_id -> chosen_letter] (multi-question map)
    Returns per-question breakdown with correct answers and explanations.
    """
    content_data = json.loads(step.content_data or "{}")
    questions: list[dict] = content_data.get("questions", [])

    if isinstance(answers, list):
        ans_map: dict = {str(a.get("question_id", "")): str(a.get("answer", "")) for a in answers}
    else:
        ans_map = {str(k): str(v) for k, v in (answers or {}).items()}

    if not questions:
        return await _llm_evaluate_quiz(ans_map, step)

    total = len(questions)
    correct_count = 0
    items = []

    for q in questions:
        q_id = str(q.get("id", ""))
        user_ans = ans_map.get(q_id, "")
        correct_ans = str(q.get("correct_answer", "")).strip().upper()

        user_letter = user_ans.strip().upper()
        if ")" in user_letter:
            user_letter = user_letter.split(")")[0].strip()

        is_correct = user_letter == correct_ans

        options: list[str] = q.get("options", [])
        correct_option_text = next(
            (opt for opt in options if str(opt).strip().upper().startswith(correct_ans + ")")),
            ""
        )

        if is_correct:
            correct_count += 1

        items.append({
            "question_id": q_id,
            "question": q.get("question", ""),
            "correct": is_correct,
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "correct_answer_text": correct_option_text,
            "explanation": q.get("explanation", ""),
        })

    score = round(correct_count / total * 100, 1) if total > 0 else 0
    passed = score >= 60

    return {
        "score": score,
        "passed": passed,
        "feedback": {
            "summary": f"You got {correct_count}/{total} correct ({score:.0f}%)",
            "items": items,
            "suggestions": (
                "Excellent! You have mastered this topic." if score >= 80
                else "Good effort. Review the explanations for wrong answers before moving on." if score >= 60
                else "Take time to revisit the material. Focus on the topics marked wrong."
            ),
        },
    }


async def _llm_evaluate_quiz(ans_map: dict, step: Step) -> dict:
    llm = get_llm_provider()
    prompt = f"""Evaluate these quiz answers for step '{step.title}':
Answers: {json.dumps(ans_map)}

Return JSON:
{{
  "score": 75.0,
  "passed": true,
  "feedback": {{
    "summary": "Good attempt...",
    "items": [],
    "suggestions": "..."
  }}
}}"""
    return await llm.generate_with_retry(EVAL_SYSTEM_PROMPT, prompt)


async def evaluate_code(code, step: Step) -> dict:
    """
    Evaluate code submission(s) via LLM.
    code can be:
      - str  -> single code string (legacy)
      - dict -> {challenge_id: code_string} for multi-challenge
    """
    content_data = json.loads(step.content_data or "{}")
    challenges: list[dict] = content_data.get("challenges", [])

    if isinstance(code, dict) and challenges:
        return await _evaluate_multi_challenges(code, challenges, step)

    llm = get_llm_provider()
    challenge_desc = (
        content_data.get("challenge_description")
        or content_data.get("challenge")
        or step.title
    )
    test_cases = content_data.get("test_cases", [])
    code_str = code if isinstance(code, str) else json.dumps(code)

    prompt = f"""Evaluate this code for the challenge: '{challenge_desc}'

CODE:
```
{code_str[:2000]}
```
Test cases: {json.dumps(test_cases[:5])}

Return JSON:
{{
  "score": 85.0,
  "passed": true,
  "feedback": {{
    "summary": "...",
    "strengths": ["..."],
    "improvements": ["..."],
    "suggestions": "..."
  }}
}}"""
    return await llm.generate_with_retry(EVAL_SYSTEM_PROMPT, prompt)


async def _evaluate_multi_challenges(code_map: dict, challenges: list[dict], step: Step) -> dict:
    llm = get_llm_provider()

    submissions = []
    for ch in challenges:
        cid = str(ch.get("id", ""))
        user_code = str(code_map.get(cid, "")).strip()
        if not user_code:
            continue
        submissions.append({
            "id": cid,
            "title": ch.get("title", ""),
            "problem": ch.get("problem", ""),
            "expected_output": ch.get("expected_output", ""),
            "user_code": user_code[:500],
        })

    if not submissions:
        return {
            "score": 0, "passed": False,
            "feedback": {
                "summary": "No code submitted",
                "challenge_results": [],
                "suggestions": "Write your solutions and click Run & Check for each challenge.",
            },
        }

    prompt = f"""Evaluate these coding challenge submissions for step '{step.title}'.
For each submission, check if the code logically produces the expected output.

Submissions:
{json.dumps(submissions, indent=2)[:3000]}

Return JSON:
{{
  "challenge_results": [
    {{
      "id": "c1",
      "passed": true,
      "score": 90,
      "feedback": "Correct! Clean solution.",
      "correct_code": "print('Hello World')"
    }}
  ]
}}
Include one entry per submitted challenge. correct_code = shortest canonical solution."""

    raw = await llm.generate_with_retry(EVAL_SYSTEM_PROMPT, prompt)
    results: list[dict] = raw.get("challenge_results", [])

    submitted_ids = {str(s["id"]) for s in submissions}
    for ch in challenges:
        cid = str(ch.get("id", ""))
        if cid not in submitted_ids:
            results.append({"id": cid, "passed": False, "score": 0, "feedback": "Not attempted", "correct_code": ""})

    passed_count = sum(1 for r in results if r.get("passed"))
    total = len(challenges)
    score = round(passed_count / total * 100, 1) if total > 0 else 0

    return {
        "score": score,
        "passed": score >= 60,
        "feedback": {
            "summary": f"{passed_count}/{total} challenges solved ({score:.0f}%)",
            "challenge_results": results,
            "suggestions": (
                "All challenges solved! Outstanding work!" if passed_count == total
                else f"Solve the remaining {total - passed_count} challenges to complete this step."
            ),
        },
    }


async def evaluate_theory(text: str, step: Step) -> dict:
    llm = get_llm_provider()
    content_data = json.loads(step.content_data or "{}")
    rubric = content_data.get("rubric", ["Understanding", "Clarity", "Depth", "Examples"])

    prompt = f"""Evaluate this written response for '{step.title}':

RESPONSE:
{text[:2000]}

Rubric criteria: {json.dumps(rubric)}

Return JSON:
{{
  "score": 80.0,
  "passed": true,
  "feedback": {{
    "summary": "Well-written response...",
    "rubric_scores": {{"Understanding": 85, "Clarity": 80, "Depth": 75, "Examples": 80}},
    "strengths": ["..."],
    "improvements": ["..."],
    "suggestions": "..."
  }}
}}"""
    return await llm.generate_with_retry(EVAL_SYSTEM_PROMPT, prompt)


async def log_submission(
    db: AsyncSession,
    step_id: str,
    user_id: str,
    submission_type: str,
    content: dict,
    score: float,
    passed: bool,
    feedback: dict,
    time_spent_seconds: int,
) -> StepSubmission:
    existing = await db.execute(
        select(StepSubmission)
        .where(StepSubmission.step_id == step_id, StepSubmission.user_id == user_id)
    )
    attempts = len(existing.scalars().all())

    submission = StepSubmission(
        step_id=step_id,
        user_id=user_id,
        submission_type=submission_type,
        content=json.dumps(content),
        score=score,
        passed=passed,
        feedback=json.dumps(feedback),
        attempt_number=attempts + 1,
        time_spent_seconds=time_spent_seconds,
    )
    db.add(submission)
    await db.commit()
    return submission
