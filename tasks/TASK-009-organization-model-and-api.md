# TASK-009: Organization Model & CRUD API (First Vertical Slice)

**Status:** Not started
**Spec sections:** SPEC-001 §2 (Organization), §6 (EntityType management — org-scoped context)
**ADRs:** ADR-001, ADR-002
**Depends on:** TASK-004, TASK-008A

## Objective

Implement the Organization model — the root tenant record that every other table references via `organization_id` — and serve as the first consumer of the TASK-008A conventions. This task produces the first working router + service + schema + factory + tests in the repo; if anything in the 008A conventions is awkward, fix it here and update `docs/conventions.md` before moving on. Also land the `on_organization_created(db, org_id)` hook surface that later tasks (029, 032) will subscribe to for per-org seed data.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `Organization` ORM model at `backend/app/models/models.py:139` with all SPEC-001 §2 fields.
- Table `organizations` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: Pydantic schemas, service (incl. `on_organization_created` hook surface), router, factory, pagination wiring, timezone validation, audit calls, tests.

## Acceptance Criteria

- [x] Organization model with all SPEC-001 §2 fields: id, name, npi_number, tax_id, phone, address, timezone (default "UTC"), is_active, created_at, updated_at
- [x] Alembic migration creates the organization table
- [ ] Pydantic schemas for create, update, and response
- [ ] CRUD endpoints under `/api/v1/organizations` (create, list, get, update) — scoped by `settings.write` / `settings.read` permissions
- [ ] List endpoint (GET `/api/v1/organizations`) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `timezone` field validates against IANA timezone identifiers
- [ ] `is_active` toggle for tenant suspension
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Router, service, schemas, and factory follow the TASK-008A conventions verbatim. Any deviation is recorded with its rationale in `docs/conventions.md` in the same PR
- [ ] `app/services/organization_hooks.py` (or equivalent) exports `register_on_create_hook(callable)` and `on_organization_created(db, org_id)`. The hook is invoked inside the same transaction as the Organization insert, after audit write, before commit. This is the extension point TASK-029 (DocumentType/ConsentType seed) and TASK-032 (FormTemplate seed) subscribe to
- [ ] Hook failure rolls back Organization creation (same transaction, same error path as audit)
- [ ] Test: organization CRUD happy path via httpx client
- [ ] Test: organization with invalid timezone returns 422
- [ ] Test: audit log entry written on organization create
- [ ] Test: a registered hook fires on organization create; a hook that raises rolls back the create

## Files

- `backend/app/models/models.py` (Organization model)
- `backend/app/schemas/eav.py` (Organization schemas)
- `backend/app/services/eav_service.py` (Organization service methods)
- `backend/app/services/organization_hooks.py` (on_organization_created hook registry)
- `backend/app/routers/eav.py` (Organization endpoints)
- `backend/tests/factories/eav.py` (Organization factory)
- `backend/tests/test_eav/test_organizations.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- EntityType, EntityAttribute, EntityInstance (TASK-010, TASK-011)
- Tenant management via system_admin (TASK-016)
