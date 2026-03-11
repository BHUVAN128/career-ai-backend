import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.exceptions import CareerAIException

logger = structlog.get_logger()


async def career_ai_exception_handler(request: Request, exc: CareerAIException):
    logger.warning("app_exception", path=request.url.path, error=exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": exc.message},
    )


async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "error": "Internal server error"},
    )
