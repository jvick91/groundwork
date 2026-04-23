"""
Application-specific exception hierarchy.

All domain exceptions inherit from GroundworkError so the FastAPI exception
handlers in main.py can catch them uniformly and return the standard JSON
envelope defined in SPEC-007 §7.

Error codes match SPEC-007 §7.3 exactly.  Error messages and details must
never contain PHI field values (SPEC-007 §7.4).
"""

from typing import Any
from uuid import UUID


class GroundworkError(Exception):
    """Base exception for all Groundwork domain errors."""

    def __init__(
        self,
        error: str = "internal_error",
        message: str = "An unexpected error occurred.",
        status_code: int = 500,
        details: list[dict[str, Any]] | None = None,
    ):
        self.error = error
        self.message = message
        self.status_code = status_code
        self.details = details or []
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# 400
# ---------------------------------------------------------------------------

class BadRequestError(GroundworkError):
    def __init__(self, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(
            error="bad_request",
            message=message,
            status_code=400,
            details=details,
        )


class OrganizationRequiredError(GroundworkError):
    def __init__(self):
        super().__init__(
            error="organization_required",
            message="An organization context is required for this operation.",
            status_code=400,
        )


# ---------------------------------------------------------------------------
# 401
# ---------------------------------------------------------------------------

class UnauthorizedError(GroundworkError):
    def __init__(self, message: str = "Authentication is required."):
        super().__init__(
            error="unauthorized",
            message=message,
            status_code=401,
        )


class AccountInactiveError(GroundworkError):
    def __init__(self):
        super().__init__(
            error="account_inactive",
            message="This account is inactive or has been deleted.",
            status_code=401,
        )


# ---------------------------------------------------------------------------
# 403
# ---------------------------------------------------------------------------

class ForbiddenError(GroundworkError):
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(
            error="forbidden",
            message=message,
            status_code=403,
        )


class OrgAccessDeniedError(GroundworkError):
    def __init__(self):
        super().__init__(
            error="org_access_denied",
            message="You do not have an active role in the requested organization.",
            status_code=403,
        )


# ---------------------------------------------------------------------------
# 404
# ---------------------------------------------------------------------------

class NotFoundError(GroundworkError):
    def __init__(self, resource: str, resource_id: UUID):
        # `resource_id` is typed as UUID only — surface-area guard so callers
        # can't accidentally pass PHI (names, emails, etc.) into `details`
        # (SPEC-007 §7.4). Lookups by non-UUID keys should use a domain-specific
        # exception instead.
        super().__init__(
            error="not_found",
            message=f"{resource} not found.",
            status_code=404,
            details=[{"resource": resource, "resource_id": str(resource_id)}],
        )


# ---------------------------------------------------------------------------
# 409
# ---------------------------------------------------------------------------

class ConflictError(GroundworkError):
    def __init__(self, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(
            error="conflict",
            message=message,
            status_code=409,
            details=details,
        )


class StateTransitionDeniedError(GroundworkError):
    def __init__(self, resource: str, current_status: str, target_status: str):
        super().__init__(
            error="state_transition_denied",
            message=f"Cannot transition {resource} from '{current_status}' to '{target_status}'.",
            status_code=409,
            details=[{
                "resource": resource,
                "current_status": current_status,
                "target_status": target_status,
            }],
        )


class ResourceLockedError(GroundworkError):
    def __init__(self, resource: str, reason: str):
        super().__init__(
            error="resource_locked",
            message=f"{resource} is locked and cannot be modified: {reason}.",
            status_code=409,
            details=[{"resource": resource, "reason": reason}],
        )


# ---------------------------------------------------------------------------
# 422
# ---------------------------------------------------------------------------

class DomainValidationError(GroundworkError):
    """Business-rule validation failure (distinct from Pydantic schema errors)."""

    def __init__(self, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(
            error="validation_error",
            message=message,
            status_code=422,
            details=details,
        )


class BridgeRuleViolation(GroundworkError):
    def __init__(self, field: str, expected_type: str, actual_type: str):
        super().__init__(
            error="bridge_rule_violation",
            message=(
                f"Bridge rule violated on field '{field}': "
                f"expected entity type '{expected_type}', got '{actual_type}'."
            ),
            status_code=422,
            details=[{
                "field": field,
                "expected_type": expected_type,
                "actual_type": actual_type,
            }],
        )


class PrerequisiteNotMetError(GroundworkError):
    def __init__(self, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(
            error="prerequisite_not_met",
            message=message,
            status_code=422,
            details=details,
        )


# ---------------------------------------------------------------------------
# 429
# ---------------------------------------------------------------------------

class RateLimitedError(GroundworkError):
    def __init__(self):
        super().__init__(
            error="rate_limited",
            message="Too many requests. Please try again later.",
            status_code=429,
        )


# ---------------------------------------------------------------------------
# 500
# ---------------------------------------------------------------------------

class InternalError(GroundworkError):
    def __init__(self):
        super().__init__(
            error="internal_error",
            message="An unexpected error occurred.",
            status_code=500,
        )
