"""
Shared Pydantic schemas used across the application.

Domain-specific request/response schemas are added per phase in this package.

Enum convention
---------------
All status/type columns are stored in the database as UPPERCASE strings matching the
Python enum member **name** (e.g. "DRAFT", "SCHEDULED").  SQLAlchemy resolves these
back to the typed enum member at read time, so application code always works with
the enum object.  Pydantic serialises the enum by its *value* — which is also
uppercase because every StrEnum in this project sets value == name.

Always import enums from app.models.models rather than redefining them, so the ORM
models and the Pydantic schemas share one source of truth.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# Re-export every domain enum so routers and schemas can
# `from app.schemas.schemas import NoteStatus` instead of reaching into models.
from app.models.models import (  # noqa: F401
    ConsentStatus,
    FieldType,
    FormType,
    InsurancePriority,
    InvoiceStatus,
    NoteFormat,
    NoteStatus,
    PayerType,
    PaymentMethod,
    PaymentStatus,
    RoleDomain,
    SessionStatus,
)


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
    sort: str = Field(default="created_at", description="Column to sort by. Must be an indexed field.")
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


class ValidationDetail(BaseModel):
    """One entry in an error response's details array (SPEC-007 §7.2)."""

    field: str
    message: str
    code: str


class ErrorResponse(BaseModel):
    """Standard error response envelope (SPEC-007 §7.1).

    `details` carries field-level validation errors for 422s or contextual
    metadata for other error types.  It is always an array — never a dict.
    """

    error: str
    message: str
    status: int
    details: list[dict[str, Any]] = []
