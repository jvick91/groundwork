# TASK-032: FormTemplate Model & API

**Status:** Not started
**Spec sections:** SPEC-006 §2 (FormTemplate, FormTemplate schema structure), §4 (FormTemplate rules), §6 (FormTemplate management), §7
**ADRs:** ADR-002
**Depends on:** TASK-009, TASK-015

## Objective

Implement the FormTemplate model with schema validation and CRUD API. FormTemplates define reusable form structures for intake, assessment, and consent workflows. The schema JSONB field is validated against a strict structure with supported field types.

## Acceptance Criteria

- [ ] FormTemplate model with all SPEC-006 §2 fields: id, organization_id, name, slug, form_type (FormType enum: intake, assessment, consent, custom), schema (JSONB), version (default "1.0.0"), is_system_template, is_active, created_at, updated_at, deleted_at
- [ ] UNIQUE(organization_id, slug); system template slugs globally reserved
- [ ] Schema JSONB validation per SPEC-006 §2: fields array with name, label, type, required, options, placeholder, max_length, validation_regex
- [ ] Supported field types: text, textarea, number, date, boolean, select, multiselect, email, phone
- [ ] Field name: matches `[a-z][a-z0-9_]{0,63}`, unique within template
- [ ] select/multiselect require non-empty options array; other types must have null options
- [ ] Unrecognized type returns 422 `validation_error`
- [ ] fields array must contain at least one field
- [ ] `GET /api/v1/form-templates` lists active templates with `forms.read` per SPEC-006 §6
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
