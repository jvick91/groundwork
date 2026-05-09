# TASK-033: Consent Session Gate & Expiry Sweep

**Status:** Not started
**Spec sections:** SPEC-003 §4 (consent gate), §7 (consent gate as service-layer dependency); SPEC-006 §3 (expiry lifecycle), §4 (consent session gate), §7 (consent session gate implementation)
**ADRs:** ADR-006 (consent expiry sweep endpoint), ADR-009
**Depends on:** TASK-022, TASK-031

## Objective

Wire the consent session gate into the session completion path and implement consent expiry handling. A session cannot transition to completed unless the client has an active signed treatment consent on file. Expired consents are transitioned lazily at read time; the authoritative batch transition is exposed as an admin endpoint that may be invoked by any external trigger (manual, scheduled via platform-level infrastructure, etc.) per ADR-006 — the backend owns no in-process scheduler.

## Acceptance Criteria

- [ ] Session completion (`POST /sessions/{id}/complete`) checks for active signed treatment consent per SPEC-003 §4
- [ ] Consent check: ConsentType slug='treatment', status='signed', AND (expiration_date IS NULL OR expiration_date >= current date) per SPEC-006 §7
- [ ] Missing or expired consent returns 422 `prerequisite_not_met` per SPEC-003 §4
- [ ] Sessions may be scheduled, confirmed, and started without consent — only completion is blocked per SPEC-003 §4
- [ ] Lazy expiry: when a consent is queried and found past expiration_date, service transitions status to EXPIRED and writes AuditLog with null actor per SPEC-006 §3
- [ ] Expired consent is never treated as valid per SPEC-006 §3
- [ ] `POST /api/v1/admin/consents/sweep-expired` batch-transitions expired consents with per-record transactions (failed records retried on next invocation) per SPEC-006 §3 and ADR-006
- [ ] Sweep endpoint requires the `system.configure` permission; the invocation mechanism (platform cron, external scheduler, manual ops) is an infrastructure/operator concern per ADR-006
- [ ] Sweep-originated audit entries have actor_person_id = null (system-triggered) per SPEC-006 §3
- [ ] TASK-022's consent-gate stub is removed — session completion now calls the real `consent_service.has_active_treatment_consent(client_instance_id)` implemented here
- [ ] Tests from SPEC-003 §9: `test_complete_session_without_treatment_consent_returns_422`, `test_complete_session_with_expired_consent_returns_422`, `test_complete_session_with_valid_consent_succeeds`
- [ ] Tests from SPEC-006 §9: `test_expired_consent_not_treated_as_valid`, `test_cron_job_transitions_expired_consents` (exercised against the sweep endpoint), `test_cron_job_writes_audit_entry_for_expiry` (exercised against the sweep endpoint), `test_complete_session_without_treatment_consent_returns_422` (cross-domain), `test_complete_session_with_expired_consent_returns_422` (cross-domain)

## Files

- `backend/app/services/consent_service.py` (consent gate check, expiry logic, sweep routine)
- `backend/app/services/session_service.py` (integrate consent gate into complete transition)
- `backend/app/routers/admin.py` (sweep-expired endpoint)
- `backend/tests/test_compliance/test_consent_lifecycle.py` (expiry + sweep tests)
- `backend/tests/test_sessions/test_session_lifecycle.py` (consent gate tests)

## Non-goals

- Consent CRUD and basic lifecycle transitions (TASK-031)
- Billing consent checks (transitively enforced via session completion per SPEC-006 §4)
- In-process scheduler / cron runner inside the backend — invocation is external per ADR-006
