# Organization API — Follow-ups

Working list captured 2026-04-30 against the `organization-api` branch.
TASK-009 shipped; these items tighten what landed.

**Order:** #4 shipped (f7908aa). #2 closed (DB default UTC is fine; revisit when scheduling/reporting lands). #1 shipped. #3 shipped — ADR-007 Accepted 2026-05-01.

---

## 1. Validate `npi_number`, `tax_id`, `phone`, `name`

**Problem.** Free-form strings save today; bad data fails downstream (837P) instead of at the API.

**Proposal** (validate when present, fields stay nullable):
- `npi_number`: 10 digits, NPPES Luhn check.
- `tax_id`: `NN-NNNNNNN`, store normalized.
- `phone`: normalize to E.164.
- `name`: add `max_length=255`.

**Acceptance:** validators on Create/Update; invalid → 422; tests valid/invalid/omitted; SPEC-001 §Organization updated.

**Refs:** `backend/app/schemas/eav.py`, SPEC-001 §Organization.

---

## 2. Require `timezone` on create — **CLOSED 2026-04-30**

Closed without change. DB default `UTC` stays. There's no scheduling, availability, or report-rollup code yet that would render against an org's TZ, so forcing it at Create is friction without payoff. Revisit when the first feature actually depends on clinic-local time — at that point a backfill + required field becomes worth doing together.

---

## 3. Restructure `address` into discrete fields

**Problem.** Single `Text` blob; billing (837P), tax jurisdiction, geocoding need components.

**Decision:** ADR-007 (Proposed → Accepted on merge).

**Proposal:** replace `address` with `address_line1`, `address_line2`, `city`, `state` (2-char), `postal_code`, `country` (ISO-3166-1 alpha-2, default `"US"`).

**Acceptance:** Alembic migration; schemas + validators; tests; SPEC-001 updated; ADR-007 flipped to Accepted.

**Refs:** ADR-007, SPEC-001 §Organization, SPEC-005.

---

## 4. Auth stub `person_id` must be None — **BLOCKING**

**Problem.** `POST /api/v1/organizations` 500s in dev. Audit insert violates `fk_audit_logs_actor_person_id_people` because the stub returns a hardcoded `person_id` (`...0000a1`) for which no `people` row exists.

`audit_logs.actor_person_id` is nullable and SPEC-006 §7 documents `NULL` for system-initiated events. The test fixture already overrides the stub to `person_id=None`; production was never updated.

**Proposal:**
1. `AuthContext.person_id`: `UUID | None`.
2. Stub returns `person_id=None`.
3. `current_person()` short-circuits while stub is on.
4. Drop the redundant override in `tests/test_eav/test_organizations.py`.

**Out of scope:** dangling `_STUB_ORG_ID` (separate landmine; owned by TASK-013/014); real auth (TASK-014).

**Acceptance:** org create succeeds with `auth_stub_enabled=True`; AuditLog row has `actor_person_id IS NULL`; `test_stub_dependencies.py` asserts `person_id is None`; `task-logs/TASK-008A-log.md` records the contract change.

**Refs:** `app/core/security.py:27-64`, `models.py:685-703`, SPEC-006 §7, TASK-008A.
