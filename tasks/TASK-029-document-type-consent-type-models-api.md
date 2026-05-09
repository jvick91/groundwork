# TASK-029: DocumentType & ConsentType Models, Seed Data, & API

**Status:** Not started
**Spec sections:** SPEC-006 §2 (DocumentType, ConsentType), §4 (system type protection, activity checks), §6 (DocumentType management, ConsentType management)
**ADRs:** ADR-002, ADR-009
**Depends on:** TASK-004, TASK-009, TASK-015

## Objective

Implement DocumentType and ConsentType reference tables with seed data, system type protection, and CRUD APIs. These are organization-scoped lookup tables that categorize documents and consent records.

## Pre-existing artifacts (from TASK-002 scope expansion)

- `DocumentType` ORM model at `backend/app/models/models.py:716`; `ConsentType` at `:765`.
- `ConsentStatus` enum at `:121`.
- Tables `document_types`, `consent_types` created by initial migration `a68701f39fed_initial_schema.py`.
- Remaining work: seed migration (8 DocumentType slugs, 9 ConsentType slugs per-org), `on_organization_created` hook handler, Pydantic schemas, service, router, linked-resource validation, system-type protection, backfill migration for existing orgs, audit calls, tests.

## Acceptance Criteria

- [x] DocumentType model with all SPEC-006 §2 fields: id, organization_id, name, slug, linked_resource_table (nullable, valid values: session, clinical_note, invoice, entity_instance, person — invalid values return 422), is_system_type, is_active, created_at, updated_at
- [x] ConsentType model with all SPEC-006 §2 fields: id, organization_id, name, slug, is_system_type, is_active, created_at, updated_at
- [ ] UNIQUE(organization_id, slug) on both tables; because `organization_id` is NOT NULL per SPEC-006 §2, system rows are materialized per-org (not globally) and system slugs are globally reserved *within the per-org row set* (no org may override a system slug with a custom type)
- [ ] Seed DocumentType slugs: session_document, clinical_attachment, consent_form, insurance_card, referral_letter, prior_authorization, identification, intake_form per SPEC-006 §2
- [ ] Seed ConsentType slugs: treatment, telehealth, release_of_information, minor_assent, guardian_consent, hipaa_privacy_notice, financial_responsibility, medication_consent, group_therapy_consent per SPEC-006 §2
- [ ] Seeding strategy: this task registers a handler with TASK-009's `on_organization_created` hook that inserts all 8 system DocumentType rows and all 9 system ConsentType rows with `is_system_type=true` for the newly-created org. All inserts occur in the same transaction as the Organization insert, so a failure rolls back the org creation
- [ ] Backfill migration: for every Organization that already exists when this task's migration runs, insert the system DocumentType/ConsentType rows that don't already exist for that org. Idempotent — re-running the migration is a no-op
- [ ] Test: creating a new Organization via the API results in 8 system DocumentType rows and 9 system ConsentType rows attached to that org
- [ ] Test: backfill migration applied to a DB containing an org with no system types inserts the full set; applied to a DB where they already exist, inserts nothing
- [ ] DocumentType CRUD: GET/POST/PATCH/DELETE with documents.read/write permissions per SPEC-006 §6
- [ ] ConsentType CRUD: GET/POST/PATCH/DELETE with consents.read/write permissions per SPEC-006 §6
- [ ] List endpoints (GET `/api/v1/document-types` and GET `/api/v1/consent-types`) use cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] System types cannot be deleted or have slug changed — returns 409 per SPEC-006 §4
- [ ] Only active types can be used for new records per SPEC-006 §4
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-006 §9: `test_duplicate_document_type_slug_same_org_returns_409`, `test_delete_system_document_type_returns_409`, `test_duplicate_consent_type_slug_same_org_returns_409`, `test_delete_system_consent_type_returns_409`, `test_create_document_with_inactive_type_returns_422`, `test_create_consent_with_inactive_type_returns_422`

## Files

- `backend/app/models/models.py` (DocumentType, ConsentType models)
- `backend/app/schemas/compliance.py` (type schemas)
- `backend/app/services/document_service.py` (document type service)
- `backend/app/services/consent_service.py` (consent type service)
- `backend/app/routers/compliance.py` (type endpoints)
- `backend/tests/factories/compliance.py` (type factories)
- `backend/tests/test_compliance/test_document_types.py`
- `backend/tests/test_compliance/test_consent_types.py`
- `backend/alembic/versions/` (model + seed migrations)

## Non-goals

- Document upload flow (TASK-030)
- ClientConsent lifecycle (TASK-031)
