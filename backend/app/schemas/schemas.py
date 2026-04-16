"""
Shared Pydantic schemas used across the application.

Domain-specific request/response schemas are added per phase in this package.
"""

from typing import Any

from pydantic import BaseModel


class PaginationMeta(BaseModel):
    """Cursor-based pagination metadata."""

    next_cursor: str | None = None
    previous_cursor: str | None = None
    has_next: bool = False
    has_previous: bool = False
    limit: int = 25


class PaginatedResponse(BaseModel):
    """Standard paginated response envelope."""

    data: list[Any]
    pagination: PaginationMeta


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: str
    message: str
    status: int
    detail: dict[str, Any] = {}
