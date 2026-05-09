# TASK-035: Cross-Cutting Integration Tests

**Status:** Not started
**Spec sections:** SPEC-007 §13.6 (test_cross_cutting/); SPEC-000 §5 (testing strategy); SPEC-006 §4 (BR-08)
**ADRs:** ADR-009
**Depends on:** TASK-003, TASK-004, TASK-006, TASK-007, TASK-008, TASK-011C, TASK-014, TASK-015, TASK-021, TASK-023, TASK-027, TASK-030, TASK-031

## Objective

Write the cross-cutting integration test suite that verifies platform-wide behaviors: multi-tenancy isolation, PHI exclusion from logs and audit snapshots, cursor pagination correctness, and error response format consistency. These tests exercise behaviors that span multiple domains rather than testing any single domain.

## Acceptance Criteria

- [ ] `test_cross_cutting/test_multi_tenancy.py`: verify that list endpoints for all major resources (instances, sessions, invoices, notes, documents, consents) filter by organization_id and never leak cross-tenant data
- [ ] `test_cross_cutting/test_phi_exclusion.py`: verify structlog PHI filter strips all BR-08 fields; verify AuditLog snapshots exclude PHI fields; verify error messages never contain PHI values per SPEC-007 §7.4
- [ ] `test_cross_cutting/test_pagination.py`: verify cursor pagination across at least two domain endpoints; verify stable results under concurrent inserts; verify limit max 100 enforced; verify sort on non-indexed column returns 400
- [ ] `test_cross_cutting/test_error_responses.py`: verify all standard error codes from SPEC-007 §7.3 return correct HTTP status and envelope shape; verify 422 validation errors include field-level details; verify 500 never leaks internals
- [ ] `test_cross_cutting/test_permission_enforcement.py`: iterates `app.routes`, filters out the exempt-route allowlist (`/health`, `/health/ready`, `/openapi.json`, `/docs`, `/redoc`, JWKS callback), and for each remaining route asserts that the handler's `Depends(...)` chain contains a call to `require_permission(...)`. Test failure message names the unguarded route path + method so the gap is actionable.
- [ ] `test_cross_cutting/test_audit_matrix.py`: parameterize over SPEC-006 §5 audit coverage matrix (every resource_type × action pair), exercise a state-changing call that produces that pair, and assert exactly one matching AuditLog row is written per BR-07
- [ ] Tests use real database, real HTTP, and real middleware — no mocks per SPEC-000 §5
- [ ] All tests pass in Docker via `docker compose exec backend pytest tests/test_cross_cutting/ -v`

## Files

- `backend/tests/test_cross_cutting/test_multi_tenancy.py`
- `backend/tests/test_cross_cutting/test_phi_exclusion.py`
- `backend/tests/test_cross_cutting/test_pagination.py`
- `backend/tests/test_cross_cutting/test_error_responses.py`
- `backend/tests/test_cross_cutting/test_permission_enforcement.py`
- `backend/tests/test_cross_cutting/test_audit_matrix.py`

## Non-goals

- Domain-specific test cases (those are in each domain's task)
- E2E browser tests (post-MVP frontend)
