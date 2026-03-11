from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.diagnosis import (
    DiagnosisResult, AssessmentStartRequest,
    AssessmentSubmitRequest, AssessmentQuestionsResponse,
)
from app.schemas.common import ApiResponse
from app.services import diagnosis as diagnosis_service
from app.services import roadmap_engine
from app.services import analytics_engine

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.post("/upload-resume", response_model=ApiResponse[DiagnosisResult])
async def upload_resume(
    file: UploadFile = File(None),
    resume_text: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Parse resume (file upload or raw text) and return diagnosis."""
    text = ""

    if file and file.filename:
        content = await file.read()

        # 10 MB file size limit
        if len(content) > 10 * 1024 * 1024:
            return ApiResponse.fail("File too large. Please upload a resume under 10 MB.")

        filename = file.filename.lower()
        if filename.endswith(".pdf"):
            try:
                import io
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                text = "\n".join(page.extract_text() or "" for page in pdf_reader.pages)
                if not text.strip():
                    return ApiResponse.fail(
                        "Could not extract text from this PDF. It may be scanned/image-based. "
                        "Try a .docx file or paste your resume text directly."
                    )
            except Exception as e:
                return ApiResponse.fail(
                    f"Could not parse PDF: {str(e)[:120]}. "
                    "Try uploading a .docx file or paste your resume text instead."
                )
        elif filename.endswith((".docx", ".doc")):
            try:
                import io
                from docx import Document
                doc = Document(io.BytesIO(content))
                text = "\n".join(para.text for para in doc.paragraphs)
            except Exception as e:
                return ApiResponse.fail(
                    f"Could not parse DOCX: {str(e)[:120]}. "
                    "Try pasting your resume text directly instead."
                )
        elif filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
            # Image-based resume: use Gemini vision to extract text
            try:
                import base64
                from app.config import settings
                from app.services.llm.factory import get_llm_provider
                import google.generativeai as genai  # type: ignore

                if not settings.GOOGLE_API_KEY:
                    return ApiResponse.fail(
                        "Image resume parsing requires a Google API key. "
                        "Please paste your resume text instead."
                    )
                genai.configure(api_key=settings.GOOGLE_API_KEY)
                vision_model = genai.GenerativeModel("gemini-1.5-flash")
                img_data = base64.b64encode(content).decode()
                ext_to_mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
                mime = ext_to_mime.get("." + filename.rsplit(".", 1)[-1], "image/jpeg")
                response = vision_model.generate_content([
                    {
                        "inline_data": {"mime_type": mime, "data": img_data}
                    },
                    "Extract all text from this resume image. Return only the extracted text, no commentary."
                ])
                text = response.text or ""
                if not text.strip():
                    return ApiResponse.fail("Could not extract text from the image. Please paste your resume text instead.")
            except Exception as e:
                return ApiResponse.fail(f"Image parsing failed: {str(e)[:120]}. Please paste your resume text instead.")
        else:
            try:
                text = content.decode("utf-8")
            except Exception:
                return ApiResponse.fail("Unsupported file type. Please upload a PDF, DOCX, or TXT file.")
    elif resume_text:
        text = resume_text
    else:
        return ApiResponse.fail("Provide either a resume file or resume_text")

    if len(text.strip()) < 50:
        return ApiResponse.fail("Resume content is too short to analyze")

    result = await diagnosis_service.parse_resume(text)
    await diagnosis_service.save_diagnosis_to_profile(db, current_user.id, result)
    return ApiResponse.ok(result)


@router.post("/start-assessment", response_model=ApiResponse[AssessmentQuestionsResponse])
async def start_assessment(
    body: AssessmentStartRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate adaptive assessment questions (no DB needed — stateless)."""
    questions = await diagnosis_service.generate_assessment_questions(body.level, body.domain)
    return ApiResponse.ok(questions)


@router.post("/submit-assessment", response_model=ApiResponse[DiagnosisResult])
async def submit_assessment(
    body: AssessmentSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate assessment and generate roadmap."""
    from app.core.exceptions import LLMError
    try:
        result = await diagnosis_service.evaluate_assessment(body.answers, body.level, body.domain)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"Assessment evaluation failed: {str(exc)[:200]}") from exc

    await diagnosis_service.save_diagnosis_to_profile(db, current_user.id, result)

    # Auto-generate roadmap
    skill_dict = {s.skill: s.score for s in result.skill_matrix}
    try:
        await roadmap_engine.generate_roadmap(
            db=db,
            user_id=current_user.id,
            domain=result.recommended_domain,
            level=result.detected_level,
            skill_matrix=skill_dict,
        )
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"Roadmap generation failed: {str(exc)[:200]}") from exc

    # Initialize skill scores honestly: cap at 25 to avoid inflated starting scores.
    # Actual scores improve as users complete quizzes and coding challenges.
    honest_skill_dict = {skill: min(score * 0.25, 25) for skill, score in skill_dict.items()}
    await analytics_engine.update_skill_scores(db, current_user.id, honest_skill_dict)

    return ApiResponse.ok(result)
