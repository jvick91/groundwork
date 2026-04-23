# TASK-020: AppointmentType Model & API

**Status:** Not started
**Spec sections:** SPEC-003 §2 (AppointmentType), §5 (intake status gate, duration consistency), §6 (AppointmentType management)
**ADRs:** ADR-002
**Depends on:** TASK-004, TASK-009, TASK-015, TASK-025

## Objective

Implement the AppointmentType model and its management API. AppointmentTypes are reusable templates defining session defaults (duration, billing code, telehealth flag, intake flag). Management is gated by `settings.write` since appointment types are organizational configuration.

The dependency on TASK-025 is load-bearing: `AppointmentType.cpt_code_id` is a FK to `CPTCode`, so the CPTCode table must exist before AppointmentType's migration runs. Phase ordering in STATE.md is conceptual grouping — the critical path for TASK-020 goes through TASK-025.

## Acceptance Criteria

- [ ] AppointmentType model with all SPEC-003 §2 fields: id, organization_id, name, default_duration_minutes, cpt_code_id (nullable FK to CPTCode), is_telehealth, is_intake, is_active, created_at, updated_at
- [ ] `GET /api/v1/appointment-types` lists active types with `sessions.read` permission per SPEC-003 §6
- [ ] List endpoint (GET `/api/v1/appointment-types`) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `POST /api/v1/appointment-types` creates type with `settings.write` permission per SPEC-003 §6
- [ ] `GET /api/v1/appointment-types/{id}` retrieves detail with `sessions.read`
- [ ] `PATCH /api/v1/appointment-types/{id}` updates with `settings.write`
- [ ] `DELETE /api/v1/appointment-types/{id}` deactivates (sets is_active=false) with `settings.write`
- [ ] Org-scoped: all queries filter by organization_id
- [ ] State changes write AuditLog rows per TASK-006 convention (BR-07)
- [ ] Tests: CRUD happy path, deactivation toggle

## Files

- `backend/app/models/models.py` (AppointmentType model)
- `backend/app/schemas/sessions.py` (AppointmentType schemas)
- `backend/app/services/session_service.py` (appointment type service methods)
- `backend/app/routers/sessions.py` (appointment type endpoints)
- `backend/tests/factories/sessions.py` (AppointmentType factory)
- `backend/tests/test_sessions/test_appointment_types.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Session model and CRUD (TASK-021)
