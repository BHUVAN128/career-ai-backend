from typing import Generic, TypeVar, Any
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: str | None = None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, error: str) -> "ApiResponse[None]":
        return cls(success=False, data=None, error=error)


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T] = []
    total: int = 0
    page: int = 1
    per_page: int = 20
    error: str | None = None


class MessageResponse(BaseModel):
    message: str
