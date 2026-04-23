# TASK-003: Error Response Contract & Exception Handling

**Status:** Complete
**Spec sections:** SPEC-007 §7 (all subsections)
**ADRs:** —
**Depends on:** TASK-001

## Objective

Implement the standard error response envelope and all custom exception classes from SPEC-007 §7.3. Register global exception handlers on the FastAPI app so every error — validation, domain, HTTP, unhandled — returns the canonical `{error, message, status, details}` shape. Ensure error messages never contain PHI per SPEC-007 §7.4.

## Acceptance Criteria

- [x] Error response Pydantic model: `{error: str, message: str, status: int, details: list}` — `ErrorResponse` updated to use `details: list[dict]` per SPEC-007 §7.1; `ValidationDetail` model added for `{field, message, code}` shape
- [x] Validation error details include `{field, message, code}` per SPEC-007 §7.2
- [x] Exception classes for all SPEC-007 §7.3 error codes: `bad_request`, `organization_required`, `unauthorized`, `account_inactive`, `forbidden`, `org_access_denied`, `not_found`, `conflict`, `state_transition_denied`, `resource_locked`, `validation_error` (as `DomainValidationError`), `bridge_rule_violation`, `prerequisite_not_met`, `rate_limited`, `internal_error`
- [x] Global exception handler catches FastAPI `RequestValidationError` and returns 422 with `{field, message, code}` details
- [x] Global exception handler returns standard envelope with status 500 and no internal details leaked — verified by `test_global_handler_returns_generic_500_without_internals`
- [x] Error messages never contain PHI field values per SPEC-007 §7.4
- [x] Tests verify each error code returns correct HTTP status and envelope shape


## Files

- `backend/app/core/exceptions.py`
- `backend/app/schemas/schemas.py` (error response models)
- `backend/app/main.py` (exception handler registration)
- `backend/tests/test_cross_cutting/test_error_responses.py`

## Non-goals

- Domain-specific error triggers (those are tested in domain tasks)
