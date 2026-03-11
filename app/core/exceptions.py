from fastapi import HTTPException, status


class CareerAIException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(CareerAIException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} not found", 404)


class UnauthorizedError(CareerAIException):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, 401)


class ForbiddenError(CareerAIException):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, 403)


class ValidationError(CareerAIException):
    def __init__(self, message: str):
        super().__init__(message, 422)


class LLMError(CareerAIException):
    def __init__(self, message: str = "LLM service error"):
        super().__init__(message, 503)


class DatabaseError(CareerAIException):
    def __init__(self, message: str = "Database error"):
        super().__init__(message, 500)


def raise_http(status_code: int, detail: str):
    raise HTTPException(status_code=status_code, detail=detail)


credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)
