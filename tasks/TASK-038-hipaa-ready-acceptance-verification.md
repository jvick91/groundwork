# TASK-038: HIPAA-Ready Acceptance Gate Verification

**Status:** Not started
**Spec sections:** SPEC-000 §6 (HIPAA-ready acceptance criteria)
**ADRs:** ADR-005 (file storage & encryption), ADR-009
**Depends on:** TASK-013, TASK-014, TASK-029, TASK-030, TASK-035

## Objective

Provide a single composite verification pass that confirms the six HIPAA-ready acceptance gates defined in SPEC-000 §6. Individual domain tasks implement the underlying capabilities; this task ensures the composite is verified end-to-end before a production release. The gates are:

1. MFA-capable auth
2. Soft delete on all PHI-bearing tables
3. AuditLog coverage for every state change
4. PHI exclusion from logs, audit snapshots, and error messages
5. S3 server-side encryption on document storage
6. Seeded ConsentTypes

## Acceptance Criteria

- [ ] **Gate 1 (MFA-capable auth):** A documentation artifact under `backend/docs/compliance/mfa-configuration.md` records the Auth0 tenant configuration that enforces MFA capability per SPEC-000 §6. The doc is reviewed as part of the release checklist.
- [ ] **Gate 2 (Soft delete on PHI tables):** `test_cross_cutting/test_hipaa_gates.py::test_phi_tables_have_soft_delete` introspects the ORM metadata and asserts every PHI-bearing table (Person, EntityInstance, Session, ClinicalNote, Invoice, InvoiceLineItem, Document, ClientConsent, FormTemplate) exposes a `deleted_at` column and that its default list endpoint excludes soft-deleted rows per BR-05
- [ ] **Gate 3 (AuditLog coverage):** This gate re-uses `test_cross_cutting/test_audit_matrix.py` from TASK-035; TASK-038 adds a composite pass/fail marker via `pytest -k hipaa_ready` so the matrix counts toward the release gate
- [ ] **Gate 4 (PHI exclusion):** This gate re-uses `test_cross_cutting/test_phi_exclusion.py` from TASK-035 under the same `hipaa_ready` marker
- [ ] **Gate 5 (S3 SSE enabled):** `test_hipaa_gates.py::test_document_encryption_default` confirms (a) new Document rows default to `is_encrypted = true`, and (b) a runtime check fetches the target bucket's `GetBucketEncryption` configuration and asserts either SSE-S3 or SSE-KMS is the default per ADR-005. In test environments without AWS access, the bucket check is skipped with a clear xfail marker and the release checklist carries the manual verification item.
- [ ] **Gate 6 (ConsentTypes seeded):** `test_hipaa_gates.py::test_seed_consent_types_present` asserts the 9 seed ConsentType slugs from SPEC-006 §2 (`treatment`, `telehealth`, `release_of_information`, `minor_assent`, `guardian_consent`, `hipaa_privacy_notice`, `financial_responsibility`, `medication_consent`, `group_therapy_consent`) are present with `is_system_type = true` after migration
- [ ] Running `docker compose exec backend pytest -k hipaa_ready` executes all six gates and exits 0 only when every gate passes
- [ ] Release checklist under `backend/docs/compliance/release-checklist.md` references Gates 1 and 5 (manual) and the `hipaa_ready` pytest marker (automated)

## Files

- `backend/tests/test_cross_cutting/test_hipaa_gates.py`
- `backend/docs/compliance/mfa-configuration.md`
- `backend/docs/compliance/release-checklist.md`

## Non-goals

- Implementing the underlying controls — those are owned by TASK-013 (seed), TASK-014 (auth), TASK-029 (ConsentType seed), TASK-030 (encryption default), TASK-035 (audit + PHI cross-cutting tests)
- Operational HIPAA compliance beyond the six platform-level gates (BAA, physical security, workforce training, etc. are out of scope for platform code)
