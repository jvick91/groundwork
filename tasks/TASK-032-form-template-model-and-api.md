# TASK-032: FormTemplate Model & API

**Status:** Not started
**Spec sections:** SPEC-006 §2 (FormTemplate, FormTemplate schema structure), §4 (FormTemplate rules), §6 (FormTemplate management), §7
**ADRs:** ADR-002
**Depends on:** TASK-004, TASK-009, TASK-015

## Objective

Implement the FormTemplate model with schema validation and CRUD API. FormTemplates define reusable form structures for intake, assessment, and consent workflows. The schema JSONB field is validated against a strict structure with supported field types.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `FormTemplate` ORM model at `backend/app/models/models.py:821` (with `SoftDeleteMixin`).
- `FormType` enum at `:128`.
- Table `form_templates` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: Pydantic schemas (incl. schema-JSONB validators), `on_organization_created` hook handler, service, router, factory, system-template protection, schema-change version bump, backfill migration for existing orgs, audit calls, tests.

## Acceptance Criteria

- [x] FormTemplate model with all SPEC-006 §2 fields: id, organization_id, name, slug, form_type (FormType enum: intake, assessment, consent, custom), schema (JSONB), version (default "1.0.0"), is_system_template, is_active, created_at, updated_at, deleted_at
- [ ] UNIQUE(organization_id, slug); because `organization_id` is NOT NULL and SPEC-006 §2 specifies "System templates are seeded per-org on organization creation," system rows are materialized per-org. System slugs are globally reserved within each org's template set (custom templates cannot shadow a system slug)
- [ ] Seeding strategy: this task registers a handler with TASK-009's `on_organization_created` hook that inserts the platform's system FormTemplate rows for the newly-created org, in the same transaction as the Organization insert
- [ ] System FormTemplate content: the initial set may be an empty list (no platform-shipped templates) or a small starter set at the implementer's discretion — the hook and the seed machinery must exist even if the starter set is empty, so later tasks can add system templates without re-plumbing the seeding path
- [ ] Backfill migration: for every Organization that already exists when this task's migration runs, insert the system FormTemplate rows that don't already exist for that org. Idempotent
- [ ] Schema JSONB validation per SPEC-006 §2: fields array with name, label, type, required, options, placeholder, max_length, validation_regex
- [ ] Supported field types: text, textarea, number, date, boolean, select, multiselect, email, phone
- [ ] Field name: matches `[a-z][a-z0-9_]{0,63}`, unique within template
- [ ] select/multiselect require non-empty options array; other types must have null options
- [ ] Unrecognized type returns 422 `validation_error`
- [ ] fields array must contain at least one field
- [ ] `GET /api/v1/form-templates` lists active templates with `forms.read` per SPEC-006 §6
- [ ] List endpoint (GET `/api/v1/form-templates`) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `POST /api/v1/form-templates` creates with `forms.write`
- [ ] `GET /api/v1/form-templates/{id}` retrieves with schema with `forms.read`
- [ ] `PATCH /api/v1/form-templates/{id}` updates (system templates: slug/form_type blocked) with `forms.write`
- [ ] `DELETE /api/v1/form-templates/{id}` deactivates with `forms.write`
- [ ] System templates cannot be deleted or have slug/form_type changed per SPEC-006 §4
- [ ] Schema change auto-increments version (semantic minor bump) if caller omits version per SPEC-006 §7
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-006 §9: `test_duplicate_form_template_slug_same_org_returns_409`, `test_delete_system_template_returns_409`, `test_patch_schema_auto_increments_version`, `test_soft_deleted_template_excluded_from_list`, `test_list_templates_filters_by_org`

## Files

- `backend/app/models/models.py` (FormTemplate model)
- `backend/app/schemas/compliance.py` (FormTemplate schemas, schema validation model)
- `backend/app/services/form_service.py` (form template service)
- `backend/app/routers/compliance.py` (form template endpoints)
- `backend/tests/factories/compliance.py` (FormTemplate factory)
- `backend/tests/test_compliance/test_form_templates.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Form submission/response tracking (post-MVP)
- Sending forms to clients (post-MVP endpoint)
