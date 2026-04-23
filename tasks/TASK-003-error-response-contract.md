# TASK-003: Error Response Contract & Exception Handling

**Status:** Not started
**Spec sections:** SPEC-007 §7 (all subsections)
**ADRs:** —
**Depends on:** TASK-001

## Objective

Implement the standard error response envelope and all custom exception classes from SPEC-007 §7.3. Register global exception handlers on the FastAPI app so every error — validation, domain, HTTP, unhandled — returns the canonical `{error, message, status, details}` shape. Ensure error messages never contain PHI per SPEC-007 §7.4.

## Acceptance Criteria

- [ ] Error response Pydantic model: `{error: str, message: str, status: int, details: list}`
- [ ] Validation error details include `{field, message, code}` per SPEC-007 §7.2
- [ ] Exception classes for all SPEC-007 §7.3 error codes: `bad_request` (400), `organization_required` (400), `unauthorized` (401), `account_inactive` (401), `forbidden` (403), `org_access_denied` (403), `not_found` (404), `conflict` (409), `state_transition_denied` (409), `resource_locked` (409), `validation_error` (422), `bridge_rule_violation` (422), `prerequisite_not_met` (422), `rate_limited` (429), `internal_error` (500)
- [ ] Global exception handler catches Pydantic `ValidationError` and returns 422 with field details
- [ ] Global exception handler returns the standard error envelope with status 500 and no internal details leaked — verified by `test_global_handler_returns_generic_500_without_internals`
- [ ] Error messages never contain PHI field values per SPEC-007 §7.4
- [ ] Tests verify each error code returns correct HTTP status and envelope shape

## Files

- `backend/app/core/exceptions.py`
- `backend/app/schemas/schemas.py` (error response models)
- `backend/app/main.py` (exception handler registration)
- `backend/tests/test_cross_cutting/test_error_responses.py`

## Non-goals

- Domain-specific error triggers (those are tested in domain tasks)
