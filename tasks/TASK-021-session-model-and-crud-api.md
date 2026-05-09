# TASK-021: Session Model & CRUD API

**Status:** Not started
**Spec sections:** SPEC-003 §2 (Session), §4 (BR-01, BR-02, bridge rules, cancellation reason, AppointmentType guard, soft delete), §5 (intake status gate, duration override), §6 (Session management, POST/PATCH schemas, response body)
**ADRs:** ADR-001, ADR-002, ADR-009
**Depends on:** TASK-004, TASK-011C, TASK-015, TASK-020

## Objective

Implement the Session model with CRUD endpoints. Enforce business rules at create time: time order (BR-01), org membership (BR-02), bridge rules for provider/client instances, inactive AppointmentType guard, intake status gate, and duration override flag. Session status transitions are handled in TASK-022.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `Session` ORM model at `backend/app/models/models.py:404` (with `SoftDeleteMixin`).
- `SessionStatus` enum at `:63`.
- Table `sessions` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: Pydantic schemas, service (BR-01/BR-02/bridge rules/intake gate/duration override), router, factory, row-level `own_sessions` filtering, audit calls, tests.

## Acceptance Criteria

- [x] Session model with all SPEC-003 §2 fields: id, organization_id, appointment_type_id, provider_instance_id, client_instance_id, start_time, end_time, status (SessionStatus enum, default SCHEDULED), cancellation_reason, cancelled_at, cancelled_by_person_id, location, notes (max 2000 chars), created_at, updated_at, deleted_at
- [ ] `POST /api/v1/sessions` with request body per SPEC-003 §6: appointment_type_id, provider_instance_id, client_instance_id, start_time, end_time, override_duration (optional), location, notes
- [ ] `GET /api/v1/sessions` lists sessions with pagination, filterable by status, provider, client, date range per SPEC-003 §6
- [ ] List endpoint (GET /api/v1/sessions) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `GET /api/v1/sessions/{id}` retrieves session detail
- [ ] `PATCH /api/v1/sessions/{id}` updates fields; provider_instance_id and client_instance_id are immutable (409 `resource_locked`) per SPEC-003 §6
- [ ] `DELETE /api/v1/sessions/{id}` soft deletes with `sessions.write`
- [ ] BR-01: end_time must be strictly after start_time; zero-duration rejected per SPEC-003 §4
- [ ] BR-02: client and provider instances must belong to same org as session per SPEC-003 §4
- [ ] Bridge rules: provider_instance_id must reference provider-type EntityInstance; client_instance_id must reference client-type per SPEC-003 §4
- [ ] Provider organization membership check: provider must have at least one active (revoked_at IS NULL) PersonRole in the session's org with primary_domain = provider, otherwise create returns 422 `bridge_rule_violation` per SPEC-003 §5
- [ ] AppointmentType guard: inactive type (is_active=false) rejected on create per SPEC-003 §4
- [ ] Intake status gate: client with intake_status="new" only allowed for is_intake=true types; others return 422 `prerequisite_not_met` per SPEC-003 §5
- [ ] Duration override: if duration < default_duration_minutes and override_duration not true, return 422 per SPEC-003 §5
- [ ] Row-level filtering: `own_sessions` condition from SPEC-002 §6 applied on list endpoints
- [ ] Soft-deleted sessions excluded from list per BR-05
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Response body matches SPEC-003 §6 schema
- [ ] Tests from SPEC-003 §9: `test_create_session_end_before_start_returns_422`, `test_create_session_zero_duration_returns_422`, `test_create_session_client_different_org_returns_422`, `test_create_session_provider_different_org_returns_422`, `test_create_session_provider_not_provider_type_returns_422`, `test_create_session_client_not_client_type_returns_422`, `test_create_session_with_inactive_type_returns_422`, `test_soft_deleted_session_excluded_from_list`, `test_list_sessions_filters_by_org`, `test_create_session_writes_audit_log`

## Files

- `backend/app/models/models.py` (Session model)
- `backend/app/schemas/sessions.py` (Session schemas)
- `backend/app/services/session_service.py` (session service)
- `backend/app/routers/sessions.py` (session endpoints)
- `backend/tests/factories/sessions.py` (Session factory)
- `backend/tests/test_sessions/test_session_crud.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Status transitions (TASK-022)
- Overlap detection (TASK-022)
- Consent gate (TASK-022 + TASK-033)
