# TASK-031: ClientConsent Model & Lifecycle API

**Status:** Not started
**Spec sections:** SPEC-006 §2 (ClientConsent), §3 (consent status lifecycle), §4 (consent rules), §6 (ClientConsent management)
**ADRs:** ADR-002, ADR-003 (partial unique indexes for one-signed-per-type)
**Depends on:** TASK-004, TASK-006, TASK-011C, TASK-029, TASK-030, TASK-032

## Dependency Note

`ClientConsent.document_id` is a FK to `Document` (TASK-030) and `ClientConsent.form_template_id` is a FK to `FormTemplate` (TASK-032). Both must exist at migration time. The original dep list omitted 030 and 032, which would have broken the migration.

## Objective

Implement the ClientConsent model with its lifecycle (pending→signed→revoked/expired) and CRUD/transition API. Endpoints follow EAV routing conventions. Enforce one-signed-per-type per client and revocation reason requirements.

## Acceptance Criteria

- [ ] ClientConsent model with all SPEC-006 §2 fields: id, organization_id, client_instance_id, consent_type_id, status (ConsentStatus enum), signed_at, signed_by_person_id, effective_date, expiration_date, revoked_at, revoked_by_person_id, revocation_reason, document_id (nullable FK to Document), form_template_id (nullable FK to FormTemplate), notes (PHI — excluded from logs), created_at, updated_at, deleted_at
- [ ] Consent endpoints on `/entities/{type_slug}/{id}/consents` per SPEC-006 §6
- [ ] type_slug must resolve to client; non-client returns 422 per SPEC-006 §6
- [ ] `GET .../consents` lists consent records with `consents.read`
- [ ] List endpoint (GET `/entities/{type_slug}/{id}/consents`) uses cursor-based pagination per TASK-004 and SPEC-007 §6 — `?cursor=...&limit=...`, returns `{data, next_cursor}`; never offset.
- [ ] `POST .../consents` creates consent with `consents.write`
- [ ] `GET .../consents/{consent_id}` retrieves with `consents.read`
- [ ] `PATCH .../consents/{consent_id}` updates pending consent with `consents.write`
- [ ] `POST .../consents/{consent_id}/sign` records as signed with `consents.sign` per SPEC-006 §6
- [ ] `POST .../consents/{consent_id}/revoke` revokes with required reason with `consents.revoke` per SPEC-006 §6
- [ ] Lifecycle per SPEC-006 §3: pending→signed, pending→revoked, signed→revoked, signed→expired
- [ ] Revoked and expired are terminal — transitions out return 409
- [ ] Revocation reason required; missing returns 422
- [ ] One signed consent per type per client — signing when active signed exists returns 409 per SPEC-006 §4
- [ ] Only active ConsentTypes (is_active=true) for new records per SPEC-006 §4
- [ ] Client bridge rule: client_instance_id must reference client-type EntityInstance
- [ ] ClientConsent.notes excluded from application logs per BR-08
- [ ] Soft-deleted consents excluded from list per BR-05
- [ ] All state-changing operations write AuditLog entries per BR-07
- [ ] Tests from SPEC-006 §9: `test_create_consent_with_valid_type_succeeds`, `test_create_consent_non_client_type_returns_422`, `test_sign_pending_transitions_to_signed`, `test_revoke_signed_transitions_to_revoked`, `test_revoke_without_reason_returns_422`, `test_transition_out_of_revoked_returns_409`, `test_transition_out_of_expired_returns_409`, `test_sign_consent_when_active_signed_exists_returns_409`, `test_soft_deleted_consent_excluded_from_list`, `test_list_consents_filters_by_org`

## Files

- `backend/app/models/models.py` (ClientConsent model)
- `backend/app/schemas/compliance.py` (consent schemas)
- `backend/app/services/consent_service.py` (consent service, lifecycle transitions)
- `backend/app/routers/compliance.py` (consent endpoints)
- `backend/tests/factories/compliance.py` (ClientConsent factory)
- `backend/tests/test_compliance/test_consents.py`
- `backend/tests/test_compliance/test_consent_lifecycle.py`
- `backend/alembic/versions/` (migration)

## Non-goals

- Consent session gate (TASK-033)
- Consent expiry cron (TASK-033)
