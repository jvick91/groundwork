"""
Application-specific exception hierarchy.

All domain exceptions inherit from GroundworkError so the FastAPI exception
handler in main.py can catch them uniformly and return a standard JSON envelope.
"""

from typing import Any
from uuid import UUID


class GroundworkError(Exception):
    """Base exception for all Groundwork domain errors."""

    def __init__(
        self,
        error: str = "groundwork_error",
        message: str = "An unexpected error occurred.",
        status_code: int = 500,
        detail: dict[str, Any] | None = None,
    ):
        self.error = error
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(self.message)


class NotFoundError(GroundworkError):
    def __init__(self, resource: str, resource_id: UUID | str):
        super().__init__(
            error="not_found",
            message=f"{resource} with id '{resource_id}' not found.",
            status_code=404,
            detail={"resource": resource, "resource_id": str(resource_id)},
        )


class ValidationError(GroundworkError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None):
        super().__init__(
            error="validation_error",
            message=message,
            status_code=422,
            detail=detail or {},
        )


class ConflictError(GroundworkError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None):
        super().__init__(
            error="conflict",
            message=message,
            status_code=409,
            detail=detail or {},
        )


class ForbiddenError(GroundworkError):
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(
            error="forbidden",
            message=message,
            status_code=403,
        )


class OrganizationRequiredError(GroundworkError):
    def __init__(self):
        super().__init__(
            error="organization_required",
            message="An organization context is required for this operation.",
            status_code=400,
        )


class BridgeRuleViolation(GroundworkError):
    def __init__(self, field: str, expected_type: str, actual_type: str):
        super().__init__(
            error="bridge_rule_violation",
            message=f"Bridge rule violated on field '{field}': expected '{expected_type}', got '{actual_type}'.",
            status_code=422,
            detail={
                "field": field,
                "expected_type": expected_type,
                "actual_type": actual_type,
            },
        )


class StatusTransitionError(GroundworkError):
    def __init__(self, resource: str, current_status: str, target_status: str):
        super().__init__(
            error="status_transition_error",
            message=f"Cannot transition {resource} from '{current_status}' to '{target_status}'.",
            status_code=422,
            detail={
                "resource": resource,
                "current_status": current_status,
                "target_status": target_status,
            },
        )
