# TASK-012: Person Model & CRUD API

**Status:** Shipped
**Spec sections:** SPEC-002 §2 (Person), §4 (soft delete rule, auth subject rule), §8 (Person management), §9 (Person query scoping)
**ADRs:** ADR-002, ADR-009
**Depends on:** TASK-004, TASK-009, TASK-006, TASK-008

## Objective

Implement the Person model — the tenant-independent canonical identity record — and its CRUD API. Person has no `organization_id`; tenant scoping is enforced through PersonRole joins. The `GET /people` endpoint must join through PersonRole to find people with active roles in the requesting user's organization.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `Person` ORM model at `backend/app/models/models.py:236` — tenant-independent, with `SoftDeleteMixin`.
- Table `people` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: Pydantic schemas, service, router, factory, PersonRole join for GET list scoping, PHI filter for `date_of_birth` in audit snapshots, audit calls, tests.

## Acceptance Criteria

- [x] Person model with all SPEC-002 §2 fields: id, auth_subject (unique, nullable), first_name, last_name, email (unique), phone, date_of_birth (nullable, PHI), is_active, created_at, updated_at, deleted_at
- [x] Person has no organization_id — tenant-independent per SPEC-002 §2 design note
- [ ] `GET /api/v1/people` lists people with active PersonRole in the requesting org per SPEC-002 §9
- [ ] List endpoint (GET `/api/v1/people`) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `POST /api/v1/people` creates a person record with `people.write` permission
- [ ] `GET /api/v1/people/{id}` retrieves person with `people.read` permission
- [ ] `PATCH /api/v1/people/{id}` updates person fields with `people.write` permission
- [ ] `DELETE /api/v1/people/{id}` soft-deletes with `people.delete` permission
- [ ] Soft-deleted persons excluded from list endpoints per BR-05
- [ ] `date_of_birth` excluded from application logs per BR-08
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-002 §11: `test_soft_deleted_person_excluded_from_list`
- [ ] `test_soft_deleted_person_returns_401` — **deferred to TASK-014** (auth middleware owns the 401 path; the Person model exposes the precondition this task needs, but the response code only exists once TASK-014 lands)

## Files

- `backend/app/models/models.py` (Person model)
- `backend/app/schemas/identity.py` (Person schemas)
- `backend/app/services/identity_service.py` (Person service)
- `backend/app/routers/identity.py` (Person endpoints)
- `backend/tests/factories/identity.py` (Person factory)
- `backend/tests/test_identity/test_people.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Role assignment (TASK-017)
- Auth middleware (TASK-014)
