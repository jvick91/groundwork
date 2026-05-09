"""Cursor-pagination Pydantic schemas (SPEC-007 §5)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SortDir(StrEnum):
    """Sort direction for list endpoints (SPEC-007 §5)."""

    ASC = "asc"
    DESC = "desc"


class PaginationParams(BaseModel):
    """Query parameters for cursor-based pagination (SPEC-007 §5).

    Use as a FastAPI dependency:  `params: PaginationParams = Depends()`
    """

    limit: int = Field(default=25, ge=1, le=100, description="Items per page. Maximum 100.")
    cursor: str | None = Field(default=None, description="Opaque cursor from a previous response.")
    sort: str = Field(
        default="created_at",
        description="Column to sort by. Must be an indexed field.",
    )
    sort_dir: SortDir = Field(default=SortDir.DESC, description="Sort direction: asc or desc.")


class PaginationMeta(BaseModel):
    """Cursor-based pagination metadata returned in every list response."""

    next_cursor: str | None = None
    previous_cursor: str | None = None
    has_next: bool = False
    has_previous: bool = False
    limit: int = 25


class PaginatedResponse(BaseModel):
    """Standard paginated response envelope."""

    data: list[Any]
    pagination: PaginationMeta
