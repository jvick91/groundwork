# TASK-020: AppointmentType Model & API

**Status:** Not started
**Spec sections:** SPEC-003 §2 (AppointmentType), §5 (intake status gate, duration consistency), §6 (AppointmentType management)
**ADRs:** ADR-002
**Depends on:** TASK-009, TASK-015

## Objective

Implement the AppointmentType model and its management API. AppointmentTypes are reusable templates defining session defaults (duration, billing code, telehealth flag, intake flag). Management is gated by `settings.write` since appointment types are organizational configuration.

## Acceptance Criteria

- [ ] AppointmentType model with all SPEC-003 §2 fields: id, organization_id, name, default_duration_minutes, cpt_code_id (nullable FK to CPTCode), is_telehealth, is_intake, is_active, created_at, updated_at
- [ ] `GET /api/v1/appointment-types` lists active types with `sessions.read` permission per SPEC-003 §6
- [ ] `POST /api/v1/appointment-types` creates type with `settings.write` permission per SPEC-003 §6
- [ ] `GET /api/v1/appointment-types/{id}` retrieves detail with `sessions.read`
- [ ] `PATCH /api/v1/appointment-types/{id}` updates with `settings.write`
- [ ] `DELETE /api/v1/appointment-types/{id}` deactivates (sets is_active=false) with `settings.write`
- [ ] Org-scoped: all queries filter by organization_id
- [ ] All state-changing operations write AuditLog entries per BR-07
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
- CPTCode model (TASK-025) — FK is nullable; cpt_code_id validation deferred until TASK-025 is complete
