# TASK-009: Organization Model & CRUD API

**Status:** Not started
**Spec sections:** SPEC-001 §2 (Organization), §6 (EntityType management — org-scoped context)
**ADRs:** ADR-001, ADR-002
**Depends on:** TASK-008A

## Objective

Implement the Organization model — the root tenant record that every other table references via `organization_id`. Provide CRUD endpoints for organization management. Organization is the multi-tenancy boundary for the entire platform.

## Acceptance Criteria

- [ ] Organization model with all SPEC-001 §2 fields: id, name, npi_number, tax_id, phone, address, timezone (default "UTC"), is_active, created_at, updated_at
- [ ] Alembic migration creates the organization table
- [ ] Pydantic schemas for create, update, and response
- [ ] CRUD endpoints under `/api/v1/organizations` (create, list, get, update) — scoped by `settings.write` / `settings.read` permissions
- [ ] `timezone` field validates against IANA timezone identifiers
- [ ] `is_active` toggle for tenant suspension
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Test: organization CRUD happy path
- [ ] Test: organization with invalid timezone returns 422

## Files

- `backend/app/models/models.py` (Organization model)
- `backend/app/schemas/eav.py` (Organization schemas)
- `backend/app/services/eav_service.py` (Organization service methods)
- `backend/app/routers/eav.py` (Organization endpoints)
- `backend/tests/factories/eav.py` (Organization factory)
- `backend/tests/test_eav/test_organizations.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- EntityType, EntityAttribute, EntityInstance (TASK-010, TASK-011)
- Tenant management via system_admin (TASK-016)
