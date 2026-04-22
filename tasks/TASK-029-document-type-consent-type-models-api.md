# TASK-029: DocumentType & ConsentType Models, Seed Data, & API

**Status:** Not started
**Spec sections:** SPEC-006 §2 (DocumentType, ConsentType), §4 (system type protection, activity checks), §6 (DocumentType management, ConsentType management)
**ADRs:** ADR-002
**Depends on:** TASK-009, TASK-015

## Objective

Implement DocumentType and ConsentType reference tables with seed data, system type protection, and CRUD APIs. These are organization-scoped lookup tables that categorize documents and consent records.

## Acceptance Criteria

- [ ] DocumentType model with all SPEC-006 §2 fields: id, organization_id, name, slug, linked_resource_table (nullable, valid values: session, clinical_note, invoice, entity_instance, person — invalid values return 422), is_system_type, is_active, created_at, updated_at
- [ ] ConsentType model with all SPEC-006 §2 fields: id, organization_id, name, slug, is_system_type, is_active, created_at, updated_at
- [ ] UNIQUE(organization_id, slug) on both tables; system type slugs globally reserved
- [ ] Seed DocumentTypes: session_document, clinical_attachment, consent_form, insurance_card, referral_letter, prior_authorization, identification, intake_form per SPEC-006 §2
- [ ] Seed ConsentTypes: treatment, telehealth, release_of_information, minor_assent, guardian_consent, hipaa_privacy_notice, financial_responsibility, medication_consent, group_therapy_consent per SPEC-006 §2
- [ ] DocumentType CRUD: GET/POST/PATCH/DELETE with documents.read/write permissions per SPEC-006 §6
- [ ] ConsentType CRUD: GET/POST/PATCH/DELETE with consents.read/write permissions per SPEC-006 §6
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
