"""Standard error envelope schemas (SPEC-007 §7)."""

from typing import Any

from pydantic import BaseModel


class ValidationDetail(BaseModel):
    """One entry in an error response's details array (SPEC-007 §7.2)."""

    field: str
    message: str
    code: str


class ErrorResponse(BaseModel):
    """Standard error response envelope (SPEC-007 §7.1).

    `details` carries field-level validation errors for 422s or contextual
    metadata for other error types. It is always an array — never a dict.
    """

    error: str
    message: str
    status: int
    details: list[dict[str, Any]] = []
