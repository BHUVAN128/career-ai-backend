import time
import uuid
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        logger.info(
            "request_started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request_failed",
                request_id=request_id,
                error=str(exc),
            )
            raise

        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(
            "request_completed",
            request_id=request_id,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response
