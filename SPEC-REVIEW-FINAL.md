# Groundwork Spec Suite — Combined Final Review

**Date:** 2026-03-26
**Sources:** Autonomous Agent Readiness Audit (Claude Opus 4.6, 2026-04-15) · Comprehensive Consistency Review (10-point cross-spec check)
**Scope:** SPEC-000 through SPEC-007
**Total issues:** 46 · 45 open · 1 fixed
**Supersedes:** SPEC-REVIEW.md

---

## How to Use This Document

The **[Priority Work Queue](#priority-work-queue)** at the bottom is the primary work artifact. Issues are numbered 1–46, ordered by severity, then by dependency, then by effort. Work through them in order. Mark each row complete as you go.

Each issue section above the queue provides the full context and required fix. The queue provides the at-a-glance map.

**Effort key:** S = single targeted change (one sentence, one table row, one note) · M = multiple changes in 1–2 files · L = new section(s) added

---

## Review Criteria

| # | Criterion | Question Answered |
|---|---|---|
| A | Master Alignment | Does each sub-spec strictly adhere to SPEC-000 architecture? |
| B | Agent Actionability | Can an agent implement every requirement without human interpretation? |
| C | Cross-Spec Integrity | Do data flows across specs form a consistent, gap-free chain? |
| D | RBAC & Compliance | Does every endpoint have explicit RBAC and audit coverage? |
| E | Definition of Done | Does every feature have exact inputs/outputs for deterministic test generation? |

---

## SPEC-000: Platform Overview

### ISSUE 000-01 [OPEN · MAJOR] — Emergency Contact Field Name Mismatch

**Criterion:** A — Master Alignment
**Location:** SPEC-000 Section 1, Personas table, Client row, "Key profile fields" column

SPEC-000 lists `emergency_contact` as a single field. SPEC-001 Section 3 seed data defines two separate EntityAttributes: `emergency_contact_name` (text, not required) and `emergency_contact_phone` (text, not required). An agent reading SPEC-000 creates one EAV attribute; an agent reading SPEC-001 creates two. These are contradictory instructions.

**Required fix:** In SPEC-000 Section 1, Personas table, Client row, change `emergency_contact` to `emergency_contact_name, emergency_contact_phone`.

---

### ISSUE 000-02 [OPEN · MINOR] — Stale Table Count (24 vs 26) in SPEC-001

**Criterion:** A — Master Alignment
**Location:** SPEC-001 Section 8, ADR-001 row says "24-table inventory." SPEC-000 Section 3 header says "26 tables."

DocumentType and ConsentType were added bringing the count to 26, but SPEC-001's ADR reference was not updated. An agent validating completeness will flag a discrepancy.

**Required fix:** In SPEC-001 Section 8, ADR-001 row, change "24-table inventory" to "26-table inventory."

---

### ISSUE 000-03 [OPEN · MAJOR] — DEA Number Missing from SPEC-001 Provider Seed Attributes

**Criterion:** B — Agent Actionability
**Location:** SPEC-000 Section 1, Prescriber row lists `dea_number`. SPEC-001 Section 3 Provider seed attributes does not include it.

An agent implementing SPEC-001 seed data will not create the `dea_number` attribute. An agent implementing the Prescriber persona from SPEC-000 will expect it to exist.

**Required fix:** Add to SPEC-001 Section 3, Provider EntityAttributes table:

```
| dea_number | DEA Number | text | false |
```

---

### ISSUE 000-04 [OPEN · MINOR] — "HIPAA-ready" is Non-Deterministic

**Criterion:** B — Agent Actionability
**Location:** SPEC-000 Section 6

"HIPAA-ready" has no pass/fail criteria. An agent cannot verify compliance without a concrete checklist.

**Required fix:** Add after the bullet points in Section 6:

```
### HIPAA-ready acceptance criteria (MVP)

The MVP is considered HIPAA-ready when ALL of the following are true:
1. Auth0 is configured with MFA enabled for all provider and admin roles.
2. Every table containing PHI has a deleted_at column and no hard-delete endpoint.
3. Every state-changing API call produces an AuditLog row (verified by SPEC-006 test suite).
4. The structlog configuration excludes all fields listed in BR-08 (verified by test_phi_exclusion.py).
5. S3 buckets have SSE-S3 or SSE-KMS encryption enabled (verified by infrastructure test).
6. ClientConsent table has seed ConsentType records for treatment, telehealth, and release_of_information.
```

---

### ISSUE 000-05 [OPEN · MAJOR] — Permission Shorthand in Personas Table is Not Actionable

**Criterion:** B — Agent Actionability
**Location:** SPEC-000 Section 1, Personas table, "Key permissions" column

The personas table uses shorthand notation (`clients.rw`, `notes.rw`, `invoices.*`, `sessions.rw`) that does not match any seed permission slug. Actual slugs are `clients.read`, `clients.write`, `invoices.read`, `invoices.write`, and so on. The `rw` and `.*` shorthand is ambiguous — `invoices.*` could mean all invoice permissions or a wildcard pattern. An agent seeding the database from this column will produce incorrect permission checks. This also conflicts with the formal matrix in SPEC-002, creating two competing representations (see ISSUE 002-07).

**Required fix:** Add a note below the Personas table:

> **Note:** The "Key permissions" column in this table uses illustrative shorthand (e.g., `clients.rw`, `invoices.*`). These are not permission slugs. Authoritative permission slugs, role grants, and the complete seed matrix are defined in SPEC-002 Section 3. In any conflict, SPEC-002 takes precedence.

---

## SPEC-001: EAV Data Platform

### ISSUE 001-01 [OPEN · CRITICAL] — Missing Test Table

**Criterion:** E — Definition of Done
**Location:** SPEC-001 — no test table section exists

SPEC-001 defines 5+ business rules (BR-05, multi-tenancy isolation, bridge rule validation, system type protection, required field enforcement, ADR-004 auto-permission generation) but provides no test mapping. An agent cannot generate deterministic tests.

**Required fix:** Add a new Section 8.5 "Test Table":

```
## Test Table

| Table | Column / Constraint | Test Case | Type | Validates |
|---|---|---|---|---|
| EntityType | `is_system_type` | `test_delete_system_entity_type_returns_409` | Integration | System type protection |
| EntityType | `is_system_type` | `test_rename_system_entity_type_returns_409` | Integration | System type protection |
| EntityType | `UNIQUE(organization_id, slug)` | `test_duplicate_slug_same_org_returns_409` | Integration | Unique slug constraint |
| EntityType | `slug` | `test_system_type_slug_reserved_across_orgs` | Integration | Global slug reservation |
| EntityAttribute | `is_system_type` parent | `test_delete_seed_attribute_on_system_type_returns_409` | Integration | Seed attribute protection |
| EntityAttribute | `is_system_type` parent | `test_add_attribute_to_system_type_succeeds` | Integration | System types are extensible |
| EntityInstance | `deleted_at` | `test_soft_deleted_instance_excluded_from_list` | Integration | BR-05 |
| EntityInstance | `organization_id` | `test_list_instances_filters_by_org` | Integration | Multi-tenancy isolation |
| EntityInstance | `organization_id` | `test_create_instance_cross_tenant_returns_403` | Integration | Multi-tenancy isolation |
| EntityInstance | `entity_type_id` bridge | `test_session_with_non_provider_instance_returns_422` | Integration | Bridge rule validation |
| EntityInstance | `entity_type_id` bridge | `test_session_with_wrong_org_instance_returns_422` | Integration | Bridge rule + org check |
| AttributeValue | `UNIQUE(entity_instance_id, entity_attribute_id)` | `test_duplicate_value_same_instance_attribute_returns_409` | Integration | Unique constraint |
| AttributeValue | `is_required` parent | `test_create_instance_missing_required_field_returns_422` | Integration | Required field enforcement |
| AttributeValue | `field_type` | `test_create_value_wrong_type_returns_422` | Integration | Type validation (ADR-005) |
| AttributeValue | `field_type` enum | `test_create_enum_value_not_in_options_returns_422` | Integration | Enum option validation |
| EntityType | POST auto-permissions | `test_create_custom_type_generates_three_permissions` | Integration | ADR-004 auto-generation |
| All EAV tables | all state changes | `test_create_entity_type_writes_audit_log` | Integration | BR-07 |
| All EAV tables | all state changes | `test_update_instance_writes_audit_log` | Integration | BR-07 |
| All EAV tables | all state changes | `test_delete_instance_writes_audit_log` | Integration | BR-07 |
```

---

### ISSUE 001-02 [OPEN · MINOR] — AttributeValue Lacks Timestamps (Intent Unstated)

**Criterion:** B — Agent Actionability
**Location:** SPEC-001 Section 2, AttributeValue table

AttributeValue has no `created_at` or `updated_at`. Every other table in the system has timestamps. This is not stated as intentional, so an agent may add or omit them inconsistently.

**Required fix:** Add design note after AttributeValue table:

> **Design note:** AttributeValue intentionally omits `created_at`, `updated_at`, and `deleted_at`. Value changes are tracked exclusively through AuditLog entries on the parent EntityInstance. Values are overwritten in place. To delete a value, set it to null. There is no soft-delete mechanism on individual values.

---

### ISSUE 001-03 [OPEN · MAJOR] — "Cast by field_type at app layer" is Vague

**Criterion:** B — Agent Actionability
**Location:** SPEC-001 Section 2, AttributeValue `value` column description; ADR-005 is listed as "Pending"

An agent cannot implement Pydantic validation without knowing the exact mapping from `field_type` to Python type and validation rule.

**Required fix:** Add "AttributeValue Type Casting Rules" table after the AttributeValue definition:

```
### AttributeValue Type Casting Rules

| field_type | Storage format (text) | Python type after cast | Validation rule |
|---|---|---|---|
| text | Raw string | str | Max 10,000 characters |
| number | Decimal string (e.g., "123.45") | Decimal | Must parse as valid decimal. No NaN or Infinity. |
| date | ISO 8601 date (e.g., "2026-04-15") | date | Must parse as YYYY-MM-DD |
| bool | "true" or "false" (lowercase) | bool | Must be exactly "true" or "false" |
| enum | One of EntityAttribute.options values | str | Must be a member of the options array |
| fk | UUID string | UUID | Must be a valid UUID referencing an EntityInstance of the type specified in EntityAttribute.options |
| jsonb | JSON string | dict | Must parse as valid JSON. Max size 100KB. |
```

---

### ISSUE 001-04 [OPEN · MAJOR] — EntityType Slug Change Cascading Impact Undefined

**Criterion:** C — Cross-Spec Integrity
**Location:** SPEC-001 Section 6, EntityType PATCH note: "When a PATCH changes a custom type's slug, the request must use the old slug in the path."

Changing a slug has cascading implications: (1) dynamically-generated Permission slugs (SPEC-002 ADR-004) reference the old slug, (2) URL routing for `/entities/{type_slug}` changes. None of these cascading effects are specified.

**Required fix:** Replace the PATCH note with:

```
Slug change rules: When a PATCH changes a custom type's slug:
1. The request path uses the old slug.
2. The system must update all Permission rows where resource_slug equals the old slug
   to use the new slug. Permission.slug is recomputed as {new_slug}.{action}.
3. RolePermission.conditions values are not automatically updated. No MVP conditions
   reference type slugs directly.
4. System types (is_system_type = true) cannot have their slug changed. Return HTTP 409,
   error code `resource_locked`.
```

---

## SPEC-002: Identity and RBAC

### ISSUE 002-01 [OPEN · CRITICAL] — Missing Test Table

**Criterion:** E — Definition of Done
**Location:** SPEC-002 — no test table section exists

SPEC-002 defines 9+ business rules with no test mapping. An agent cannot generate deterministic tests.

**Required fix:** Add a "Test Table" section covering: duplicate active role (409), entity_instance_id rules (4 variants), role revocation, hierarchy domain invariant, system role protection, unique role slug, auto-permission generation, duplicate grant (409), revoked grant exclusion, auth_subject rule, is_active toggle, soft delete exclusion, multi-role union, hierarchy inheritance, tenant isolation, and 3 audit log tests.

```
## Test Table

| Table | Column / Constraint | Test Case | Type | Validates |
|---|---|---|---|---|
| PersonRole | `UNIQUE(org, person, role, instance) WHERE revoked_at IS NULL` | `test_duplicate_active_role_returns_409` | Integration | Unique constraint |
| PersonRole | `entity_instance_id` rules | `test_assign_provider_role_without_entity_instance_returns_422` | Integration | entity_instance_id required for person subtypes |
| PersonRole | `entity_instance_id` rules | `test_assign_provider_role_with_client_instance_returns_422` | Integration | Instance type must match role domain |
| PersonRole | `entity_instance_id` rules | `test_assign_provider_role_with_wrong_org_instance_returns_422` | Integration | Instance must be same org |
| PersonRole | `entity_instance_id` rules | `test_assign_system_admin_without_entity_instance_succeeds` | Integration | system_admin allows null instance |
| PersonRole | `revoked_at` | `test_revoke_role_sets_revoked_at` | Integration | Revocation rule |
| PersonRole | `revoked_at` | `test_revoked_role_excluded_from_permission_resolution` | Integration | Revocation removes access |
| Role | `primary_domain` hierarchy | `test_create_child_role_different_domain_returns_422` | Integration | Hierarchy invariant |
| Role | `is_system_role` | `test_delete_system_role_returns_409` | Integration | System role protection |
| Role | `UNIQUE(organization_id, slug)` | `test_duplicate_role_slug_same_org_returns_409` | Integration | Unique slug constraint |
| Permission | auto-generation | `test_create_entity_type_generates_read_write_delete_permissions` | Integration | ADR-004 contract |
| RolePermission | `UNIQUE(org, role, permission) WHERE revoked_at IS NULL` | `test_duplicate_active_grant_returns_409` | Integration | Unique constraint |
| RolePermission | `revoked_at` | `test_revoked_grant_excluded_from_effective_permissions` | Integration | Revocation rule |
| Person | `auth_subject` | `test_person_without_auth_subject_cannot_authenticate` | Integration | Auth subject rule |
| Person | `is_active` | `test_inactive_person_returns_401` | Integration | Soft toggle |
| Person | `deleted_at` | `test_soft_deleted_person_returns_401` | Integration | Soft delete rule |
| Person | `deleted_at` | `test_soft_deleted_person_excluded_from_list` | Integration | BR-05 |
| Authorization | multi-role union | `test_person_with_two_roles_gets_union_permissions` | Integration | Role union rule |
| Authorization | hierarchy | `test_child_role_inherits_parent_permissions` | Integration | Inheritance rule |
| Authorization | tenant isolation | `test_person_role_cross_tenant_returns_403` | Integration | Tenant isolation |
| All tables | all state changes | `test_assign_role_writes_audit_log` | Integration | BR-07 |
| All tables | all state changes | `test_revoke_role_writes_audit_log` | Integration | BR-07 |
| All tables | all state changes | `test_grant_permission_writes_audit_log` | Integration | BR-07 |
```

---

### ISSUE 002-02 [OPEN · MAJOR] — `permissions.read` Referenced but Undefined

**Criterion:** C — Cross-Spec Integrity
**Location:** SPEC-002 Section 8 `GET /permissions` requires `permissions.read`. SPEC-007 Section 8.3 requires `roles.read`. `permissions.read` does not exist in the seed permissions list.

An agent seeding the database will not create `permissions.read`. The permission check will always fail for every user.

**Required fix:** In SPEC-002 Section 8, change `GET /permissions` required permission from `permissions.read` to `roles.read`.

---

### ISSUE 002-03 [OPEN · MINOR] — No `notes.delete` Permission (Intent Unstated)

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-002 Section 3 seed permissions; SPEC-004 uses `notes.write` for soft-delete

Every other domain with soft-delete endpoints uses a dedicated `.delete` permission. Notes are the sole exception, with no stated rationale.

**Required fix:** Add design note in SPEC-002 Section 3, after the seed permissions table:

> **Design note on notes.delete:** A dedicated `notes.delete` permission is intentionally omitted. Only draft notes may be soft-deleted (BR-05), and only the author may delete their own drafts. The `notes.write` permission covers this action because draft deletion is semantically equivalent to discarding an unfinished edit, not destroying a clinical record.

---

### ISSUE 002-04 [OPEN · MAJOR] — No CPT/ICD Code Management Permissions or Endpoints

**Criterion:** C — Cross-Spec Integrity
**Location:** SPEC-002 Section 3 (only `codes.read`); SPEC-005 Section 5 (only GET endpoints)

No user can create, update, or deactivate CPT/ICD codes through the API. The tables exist with `is_active` flags and org-scoping, implying management is needed. An agent implementing billing cannot populate the code tables.

**Required fix:**
- Add to SPEC-002 Section 3 seed permissions: `codes.write` (Create or update CPT/ICD codes) and `codes.delete` (Deactivate CPT/ICD codes). Grant both to `admin` and `biller` roles in the seed matrix.
- Add to SPEC-005 Section 5: `POST /cpt-codes`, `PATCH /cpt-codes/{id}`, `DELETE /cpt-codes/{id}`, `POST /icd-codes`, `PATCH /icd-codes/{id}`, `DELETE /icd-codes/{id}` with appropriate permissions.
- Add corresponding rows to SPEC-007 Section 8.6 (see ISSUE 007-04).

---

### ISSUE 002-05 [OPEN · MAJOR] — `entity_types.read` Not Granted to Providers

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-002 Section 3 seed matrix

`entity_types.read` is granted only to the `admin` role. Providers need it to discover available type slugs for EAV instance endpoints and to populate entity type dropdowns in provider-facing UIs.

**Required fix:** In SPEC-002 Section 3 seed matrix, add `entity_types.read` as a direct grant to the `provider` role (inherited by therapist, supervisor, prescriber) and to `receptionist`.

---

### ISSUE 002-06 [OPEN · MAJOR] — /auth/me Response Shape Conflict with SPEC-007

**Criterion:** C — Cross-Spec Integrity
**Location:** SPEC-002 Section 8 (flat single-org response) vs SPEC-007 Section 3.4 (multi-org array)

Two specs define incompatible JSON shapes for the same endpoint. An agent must choose one and will violate the other. SPEC-007's multi-org array is the correct shape because `GET /auth/me` does not require `X-Organization-Id` and must return all organizations.

**Required fix:** Replace SPEC-002 Section 8 `/auth/me response shape` section with:

```
### /auth/me response shape

The response matches SPEC-007 Section 3.4. It includes person identity and all organizations
with their roles. No effective_permissions field is included — use GET /auth/me/permissions
with X-Organization-Id for the resolved permission set.

| Field | Type | Description |
|---|---|---|
| person.id | UUID | Person primary key |
| person.first_name | String | First name |
| person.last_name | String | Last name |
| person.email | String | Email address |
| organizations | Array | All orgs where the person has active roles |
| organizations[].id | UUID | Organization primary key |
| organizations[].name | String | Practice name |
| organizations[].roles | Array | Active PersonRole records in this org |
| organizations[].roles[].role_slug | String | Role machine identifier |
| organizations[].roles[].role_name | String | Role display name |
| organizations[].roles[].primary_domain | Enum | admin, provider, or client |
| organizations[].roles[].entity_instance_id | UUID, nullable | Bound profile instance |
```

---

### ISSUE 002-07 [OPEN · MAJOR] — Two Competing Role-Permission Representations

**Criterion:** B — Agent Actionability
**Location:** SPEC-000 Section 1 Personas table ("Key permissions" column) and SPEC-002 Section 3 formal seed matrix

Both files define permissions per role in different formats with different levels of detail. Combined with ISSUE 000-05 (shorthand slugs), an agent seeding the database cannot determine which is authoritative.

**Required fix:** Add a note to SPEC-000 Section 1, immediately above or below the Personas table:

> **Authoritative source:** The "Key permissions" column in this table is illustrative. Authoritative permission slugs, role grants, and the complete seed matrix are defined in SPEC-002 Section 3. In any conflict, SPEC-002 takes precedence.

---

## SPEC-003: Scheduling and Sessions

### ISSUE 003-01 [OPEN · CRITICAL] — Missing Test Table

**Criterion:** E — Definition of Done
**Location:** SPEC-003 — no test table section exists

SPEC-003 defines 9+ business rules and scheduling constraints with no test mapping.

**Required fix:** Add a "Test Table" section covering:

```
## Test Table

| Table | Column / Constraint | Test Case | Type | Validates |
|---|---|---|---|---|
| Session | `start_time` < `end_time` | `test_create_session_end_before_start_returns_422` | Integration | BR-01 |
| Session | `start_time` = `end_time` | `test_create_session_zero_duration_returns_422` | Integration | BR-01 |
| Session | `organization_id` match | `test_create_session_client_different_org_returns_422` | Integration | BR-02 |
| Session | `organization_id` match | `test_create_session_provider_different_org_returns_422` | Integration | BR-02 |
| Session | provider overlap | `test_create_overlapping_session_returns_409` | Integration | BR-03 |
| Session | provider overlap | `test_create_session_adjacent_no_overlap_succeeds` | Integration | BR-03 boundary |
| Session | provider overlap | `test_cancelled_session_not_counted_in_overlap` | Integration | BR-03 |
| Session | provider overlap | `test_no_show_session_not_counted_in_overlap` | Integration | BR-03 |
| Session | provider overlap | `test_overlap_check_concurrent_booking_uses_transaction` | Integration | BR-03 race condition |
| Session | `provider_instance_id` bridge | `test_create_session_provider_not_provider_type_returns_422` | Integration | Bridge rule |
| Session | `client_instance_id` bridge | `test_create_session_client_not_client_type_returns_422` | Integration | Bridge rule |
| Session | `status` lifecycle | `test_confirm_scheduled_succeeds` | Integration | scheduled -> confirmed |
| Session | `status` lifecycle | `test_start_confirmed_succeeds` | Integration | confirmed -> in_progress |
| Session | `status` lifecycle | `test_complete_in_progress_succeeds` | Integration | in_progress -> completed |
| Session | `status` lifecycle | `test_cancel_with_reason_succeeds` | Integration | Cancel transition |
| Session | `status` lifecycle | `test_cancel_without_reason_returns_422` | Integration | Cancellation reason required |
| Session | `status` lifecycle | `test_no_show_with_reason_succeeds` | Integration | No-show transition |
| Session | `status` lifecycle | `test_no_show_without_reason_returns_422` | Integration | Cancellation reason required |
| Session | `status` lifecycle | `test_transition_out_of_completed_returns_409` | Integration | Terminal status |
| Session | `status` lifecycle | `test_transition_out_of_cancelled_returns_409` | Integration | Terminal status |
| Session | `status` lifecycle | `test_transition_out_of_no_show_returns_409` | Integration | Terminal status |
| Session | consent gate | `test_complete_session_without_treatment_consent_returns_422` | Integration | Consent gate (SPEC-006) |
| Session | consent gate | `test_complete_session_with_expired_consent_returns_422` | Integration | Consent gate expiry check |
| Session | consent gate | `test_complete_session_with_valid_consent_succeeds` | Integration | Consent gate happy path |
| AppointmentType | `is_active` | `test_create_session_with_inactive_type_returns_422` | Integration | AppointmentType guard |
| Session | `deleted_at` | `test_soft_deleted_session_excluded_from_list` | Integration | BR-05 |
| Session | `deleted_at` | `test_soft_deleted_session_excluded_from_overlap` | Integration | Soft delete rule |
| Session | `organization_id` | `test_list_sessions_filters_by_org` | Integration | Multi-tenancy isolation |
| All tables | all state changes | `test_create_session_writes_audit_log` | Integration | BR-07 |
| All tables | all state changes | `test_cancel_session_writes_audit_log` | Integration | BR-07 |
```

---

### ISSUE 003-02 [OPEN · MAJOR] — "Shorter Durations Allowed Only if Explicitly Set" is Non-Deterministic

**Criterion:** B — Agent Actionability
**Location:** SPEC-003 Section 5, Scheduling Constraints

Every session creation requires `sessions.write`, so this clause provides no actual constraint. Two agents would implement this differently. One might require a flag; another might accept any submitted duration.

**Required fix:** Replace the constraint with:

> End-to-end duration consistency: The difference between `end_time` and `start_time` must equal or exceed the AppointmentType's `default_duration_minutes`. If the submitted duration is shorter, the request must include `override_duration: true` in the request body. Requests with a shorter duration that omit this flag are rejected with HTTP 422, error code `validation_error`, detail: "Session duration is shorter than the appointment type default. Set override_duration to true to confirm."

---

### ISSUE 003-03 [OPEN · MAJOR] — "Non-Intake Session Type" is Undefined

**Criterion:** B — Agent Actionability
**Location:** SPEC-003 Section 5, Scheduling Constraints: "A client must have an EntityInstance with intake_status of complete or in_progress before a non-intake session type can be scheduled"

`AppointmentType` has no field distinguishing intake from non-intake types. The `name` field is free-form. An agent cannot classify types.

**Required fix:** Add to AppointmentType in SPEC-003 Section 2:

```
| is_intake | Boolean | NOT NULL, default false | When true, this type can be scheduled for clients
                                                    regardless of intake_status. |
```

Then rewrite the constraint:

> Intake status gate: A client with `intake_status = "new"` may only be scheduled for AppointmentTypes where `is_intake = true`. Clients with `intake_status = "in_progress"` or `"complete"` may be scheduled for any active AppointmentType. Violations return HTTP 422, error code `prerequisite_not_met`.

---

### ISSUE 003-04 [OPEN · MAJOR] — Row-Level Filtering Not Specified for Session Endpoints

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-003 Section 6; SPEC-002 Section 6 defines `scope: own_sessions`

SPEC-003 does not specify how `scope: own_sessions` from SPEC-002 is applied to `GET /sessions`. An agent implementing this endpoint for a therapist role does not know whether to filter by `provider_instance_id`.

**Required fix:** Add to SPEC-003 Section 7, Implementation Constraints:

> Row-level filtering: When the requesting user's RolePermission grant for `sessions.read` or `sessions.write` includes conditions `{"scope": "own_sessions"}`, the query must filter Session records to only those where `provider_instance_id` matches the requesting user's EntityInstance ID (resolved from their active PersonRole). Null conditions mean unrestricted access within the organization. See SPEC-002 Section 6.

---

### ISSUE 003-05 [OPEN · MAJOR] — Session Create/Update Request Schema Not Defined

**Criterion:** E — Definition of Done
**Location:** SPEC-003 Section 6, `POST /sessions` and `PATCH /sessions/{id}`

No request body schema is defined. An agent cannot generate a Pydantic model without knowing which fields are required vs optional, and which are server-derived.

**Required fix:** Add to SPEC-003 Section 6:

```
### POST /sessions request body

| Field | Type | Required | Description |
|---|---|---|---|
| appointment_type_id | UUID | Yes | Must reference an active AppointmentType in the same org. |
| provider_instance_id | UUID | Yes | Must reference an EntityInstance of type provider in the same org. |
| client_instance_id | UUID | Yes | Must reference an EntityInstance of type client in the same org. |
| start_time | Timestamp (ISO 8601 UTC) | Yes | Session start time. |
| end_time | Timestamp (ISO 8601 UTC) | Yes | Session end time. Must be after start_time. |
| override_duration | Boolean | No | Required to be true if duration is shorter than default. |
| location | String | No | Physical address or telehealth identifier. |
| notes | String | No | Internal scheduling notes. Max 2000 characters. |

### PATCH /sessions/{id} request body

All fields optional. Only provided fields are updated. Status cannot be changed via PATCH;
use the explicit transition endpoints. provider_instance_id and client_instance_id cannot
be changed after creation; return HTTP 409, error code `resource_locked` if attempted.

### Session response body

| Field | Type | Description |
|---|---|---|
| id | UUID | Session primary key |
| organization_id | UUID | Tenant |
| appointment_type_id | UUID | Template reference |
| provider_instance_id | UUID | Provider profile |
| client_instance_id | UUID | Client profile |
| start_time | Timestamp | ISO 8601 UTC |
| end_time | Timestamp | ISO 8601 UTC |
| status | String | Current lifecycle status |
| cancellation_reason | String, nullable | Set on cancel/no-show |
| cancelled_at | Timestamp, nullable | When cancelled |
| cancelled_by_person_id | UUID, nullable | Who cancelled |
| location | String, nullable | Location |
| notes | String, nullable | Scheduling notes |
| created_at | Timestamp | Creation time |
| updated_at | Timestamp | Last modification |
```

---

## SPEC-004: Clinical Notes

### ISSUE 004-01 [OPEN · CRITICAL] — Lifecycle Contradiction (amendment_pending → cosigned)

**Criterion:** B — Agent Actionability
**Location:** SPEC-004 Section 4, Note Status Lifecycle table; Section 6, Amendment Model step 4

The lifecycle table allows `amendment_pending → cosigned`. The amendment model in Section 6 requires the author to re-sign the note before it can be co-signed. These are contradictory. An agent will implement a state path that the amendment model forbids.

**Required fix:** Remove from the SPEC-004 Section 4 lifecycle table:

```
| amendment_pending | cosigned | Any person with notes.cosign permission co-signs amended note |
```

Add note: "An amended note must be re-signed by the author before it can be co-signed. The path is always: `amendment_pending → signed → cosigned`."

---

### ISSUE 004-02 [OPEN · MINOR] — Missing Test for amendment_pending Soft Delete

**Criterion:** E — Definition of Done
**Location:** SPEC-004 Section 10, Test Table

Tests exist for `signed` and `cosigned` soft-delete protection, but not for `amendment_pending`. BR-05 states only draft notes may be soft-deleted, so `amendment_pending` deletion must be blocked.

**Required fix:** Add to SPEC-004 Section 10 test table:

```
| ClinicalNote | `deleted_at` | `test_soft_delete_amendment_pending_note_returns_409` | Integration | amendment_pending notes protected from deletion |
```

---

### ISSUE 004-03 [OPEN · MAJOR] — Amendment Append Semantics Undefined at API Level

**Criterion:** B — Agent Actionability
**Location:** SPEC-004 Section 7, `POST /sessions/{session_id}/note/amend`

No request body schema is defined. The spec says each cycle "appends to amendment_note" but an agent does not know: what field name the text is submitted under, what separator is used between amendments, or whether append is client-side or server-side.

**Required fix:** Add after the lifecycle transitions table in SPEC-004 Section 7:

```
### POST /sessions/{session_id}/note/amend request body

| Field | Type | Required | Description |
|---|---|---|---|
| amendment_text | String | Yes | The addendum text. Min 1 character, max 10,000 characters. |

The backend appends amendment_text to the existing amendment_note field using this format:
[AMENDMENT {ISO 8601 UTC timestamp} by {person first_name last_name}]
{amendment_text}

The client never sends the full amendment_note. The backend always appends.
If the request body includes an `amendment_note` field, return HTTP 422, error code
`validation_error`, message: "amendment_note cannot be set directly. Use amendment_text."
```

---

### ISSUE 004-04 [OPEN · MAJOR] — Row-Level Filtering for Notes Not Specified

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-004 Section 7; SPEC-002 Section 6 defines `scope: own_notes`

SPEC-004 does not specify how `scope: own_notes` from SPEC-002 is applied to `GET /notes`. An agent implementing the note list endpoint for a therapist does not know whether to filter by `author_instance_id`.

**Required fix:** Add to SPEC-004 Section 8, Implementation Constraints:

> Row-level filtering: When the requesting user's RolePermission grant for `notes.read` includes conditions `{"scope": "own_notes"}`, the query must filter ClinicalNote records to only those where `author_instance_id` matches the requesting user's EntityInstance ID. Null conditions mean unrestricted access within the organization. See SPEC-002 Section 6.

---

### ISSUE 004-05 [OPEN · MINOR] — Practice Admin Notes Access Boundary Unstated

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-002 Section 3 seed matrix; SPEC-004 Section 6, Amendment Model

`practice_admin` does not have `notes.write` in the seed matrix. If a practice admin needs to manage amendment workflows (e.g., requesting a provider amend a note), they have no mechanism. This may be intentional but is unstated, leaving the boundary ambiguous.

**Required fix:** Add design note in SPEC-002 Section 3, after the seed matrix:

> **Design note on practice_admin and notes:** `practice_admin` does not receive `notes.write` or `notes.sign`. Clinical note management is the exclusive domain of providers. Practice admins can view notes via `notes.read` (via admin role inheritance) but cannot create, sign, or amend them. If a practice admin identifies a note requiring amendment, they communicate this to the provider out of band.

---

## SPEC-005: Billing and Payments

### ISSUE 005-01 [OPEN · MAJOR] — Invoice Soft Delete vs Void Relationship Unclear

**Criterion:** B — Agent Actionability
**Location:** SPEC-005 Section 2 (Invoice has both `deleted_at` and `status = void`); Section 4 Business Rules

The test table includes `test_soft_delete_draft_invoice_succeeds`, implying only draft invoices can be soft-deleted, but the business rules section never states this restriction explicitly. The void and soft-delete mechanisms overlap without a clear delineation.

**Required fix:** Add to SPEC-005 Section 4, Business Rules:

> Soft delete restriction: Only invoices in `draft` status may be soft-deleted via `DELETE /invoices/{id}`. Invoices in `sent`, `partial`, `paid`, or `void` status must not be soft-deleted. To remove a non-draft invoice from active use, void it via `POST /invoices/{id}/void`. Attempts to soft-delete a non-draft invoice return HTTP 409, error code `state_transition_denied`.

---

### ISSUE 005-02 [OPEN · MAJOR] — "Partial" Status Ambiguity in Line Item Lock Rule

**Criterion:** B — Agent Actionability
**Location:** SPEC-005 Section 4, line item lock rule

First sentence excludes `paid` and `void`. Second sentence allows only `draft` and `sent`. The `partial` status falls through both sentences. An agent reading the first sentence may allow edits on partial invoices.

**Required fix:** Replace both sentences with:

> Locked invoice editing: Line items can only be added, updated, or deleted on invoices in `draft` or `sent` status. Invoices in `partial`, `paid`, or `void` status are locked. Attempts to modify line items on a locked invoice return HTTP 409, error code `resource_locked`, message: "Line items cannot be modified on invoices in {status} status."

---

### ISSUE 005-03 [OPEN · MAJOR] — Invoice Create Request Schema Missing

**Criterion:** E — Definition of Done
**Location:** SPEC-005 Section 5, `POST /invoices`

No request body schema is defined. Business rules state `client_instance_id` and `provider_instance_id` are derived from the session, but an agent reading only the Invoice table definition would include them in the request body.

**Required fix:** Add to SPEC-005 Section 5:

```
### POST /invoices request body

| Field | Type | Required | Description |
|---|---|---|---|
| session_id | UUID | Yes | Must reference a completed session in the same org. |
| notes | String | No | Internal billing notes. Max 2000 characters. |
| due_date | Date | No | Payment due date. ISO 8601. |

client_instance_id and provider_instance_id are derived from the referenced Session.
The backend copies them at creation time. They are not accepted in the request body.
If the request body includes these fields, they are ignored.

### POST /invoices response body

Returns the full Invoice object with all fields, plus an empty line_items array.
```

---

### ISSUE 005-04 [OPEN · MINOR] — Payment `insurance_payer_id` Validation Not in Business Rules

**Criterion:** E — Definition of Done
**Location:** SPEC-005 Section 8 test table includes `test_insurance_payment_without_payer_id_returns_422`; Section 4 does not state the rule

The test table defines a test for a rule that is not written. An agent implementing the service layer from the business rules will not implement this validation.

**Required fix:** Add to SPEC-005 Section 4, Business Rules:

> Insurance payer required: When `Payment.payer_type = "insurance"`, `insurance_payer_id` must be non-null and reference an active InsurancePayer in the same org. When `payer_type` is `"client"` or `"other"`, `insurance_payer_id` must be null. Violations return HTTP 422, error code `validation_error`.

---

### ISSUE 005-05 [OPEN · MINOR] — No `payments.void` Permission (Intent Unstated)

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-002 Section 3 (no `payments.void`); SPEC-005 uses `payments.record` for the void endpoint

Voiding a payment bundles with recording a payment under one permission with no stated rationale. An agent implementing fine-grained access control cannot separate these actions.

**Required fix:** Add design note in SPEC-002 Section 3:

> **Design note on payments.void:** A dedicated `payments.void` permission is intentionally omitted. Payment voiding is bundled with `payments.record` because the void-and-rerecord workflow is a single logical operation. All payment voids are tracked in AuditLog with the void reason.

---

## SPEC-006: Documents, Consent, and Compliance

### ISSUE 006-01 [OPEN · MINOR] — pending → revoked Consent Transition Semantics Ambiguous

**Criterion:** B — Agent Actionability
**Location:** SPEC-006 Section 3, Consent Status Lifecycle

"Revoked" covers both declined-before-signing and withdrawn-after-signing. Audit reports cannot distinguish the two cases without guidance.

**Required fix:** Add design note after the lifecycle table:

> **Design note:** The `revoked` terminal status covers both declined-before-signing and withdrawn-after-signing cases. The distinction is deterministic from the data: if `signed_at IS NULL` and `status = revoked`, the consent was declined before signing. If `signed_at IS NOT NULL` and `status = revoked`, the consent was withdrawn after signing. Agents and reports should use this field-level distinction rather than relying on status alone.

---

### ISSUE 006-02 [OPEN · MAJOR] — FormTemplate Schema JSONB Structure Undefined

**Criterion:** B — Agent Actionability
**Location:** SPEC-006 Section 2, FormTemplate.schema: "JSONB. Form field definitions."

An agent cannot implement Pydantic validation for `FormTemplate.schema` without knowing the exact structure. SPEC-004 solved the equivalent problem by defining exact content schemas for SOAP/DAP/BIRP formats.

**Required fix:** Add "FormTemplate Schema Structure" subsection to SPEC-006 Section 2:

```
### FormTemplate Schema Structure

The schema JSONB field must conform to this structure:

{
  "fields": [
    {
      "name": "string (required, machine name, [a-z][a-z0-9_]{0,63})",
      "label": "string (required, human-readable display label)",
      "type": "one of: text, textarea, number, date, boolean, select, multiselect, email, phone",
      "required": "boolean (required, default false)",
      "options": ["array of strings, required when type is select or multiselect, null otherwise"],
      "placeholder": "string (optional)",
      "max_length": "integer (optional)",
      "validation_regex": "string (optional)"
    }
  ]
}

Validation rules:
- The fields array must contain at least one field.
- Field names must be unique within the array.
- select and multiselect types must have a non-empty options array.
- All other types must have options = null.
```

---

### ISSUE 006-03 [OPEN · MAJOR] — Consent Expiry Task Error Handling Unspecified

**Criterion:** B — Agent Actionability
**Location:** SPEC-006 Section 3, `expire_consents` Celery Beat task

The task processes multiple records in batch. The spec does not define what happens when one record fails. Three strategies are each equally valid under the current spec: atomic batch, per-record with skip, or stop on first error.

**Required fix:** Add after the `expire_consents` description:

> Error handling: Each consent record is expired in its own database transaction. A failure on one record (e.g., constraint violation, database error) is logged at ERROR level and does not prevent processing of remaining records. Failed records are retried on the next scheduled run. The task reports the total count of successfully expired records and the count of failures in its Celery result.

---

### ISSUE 006-04 [OPEN · MINOR] — Presigned URL Expiry Window Not Specified

**Criterion:** B — Agent Actionability
**Location:** SPEC-006 Section 7: ADR-009 is listed as "Pending"

"Measured in minutes, not hours" covers a range from 1 to 59 minutes with very different security implications. ADR-009 may not be finalized before implementation begins.

**Required fix:** Replace the constraint with:

> Presigned URL expiry: S3 presigned download URLs expire after 15 minutes. S3 presigned upload URLs expire after 60 minutes. These defaults apply until ADR-009 is accepted; if ADR-009 specifies different values, it overrides these.

---

### ISSUE 006-05 [OPEN · MINOR] — DocumentType.linked_resource_table is a Free-Form String

**Criterion:** B — Agent Actionability
**Location:** SPEC-006 Section 2, DocumentType model

`linked_resource_table` is a free-form string with no defined valid values. An agent seeding document types has no guidance on valid values, and the bridge rule enforcement logic cannot be deterministically implemented.

**Required fix:** Add a design note or valid values list after the DocumentType table:

> `linked_resource_table` valid values are the concrete table names in the MVP inventory: `entity_instance`, `clinical_note`, `invoice`, `person`, or null for documents not linked to a specific record type. Return HTTP 422 for any value not in this list.

---

## SPEC-007: API Contract and Testing

### ISSUE 007-01 [OPEN · MINOR] — Stale "conductor" Reference

**Criterion:** A — Master Alignment
**Location:** SPEC-007 Section 7.3, `bridge_rule_violation` error code description

"Non-provider as session conductor" — "conductor" was renamed to "provider" in SPEC-003 v0.2.0. An agent will use the wrong terminology in error messages.

**Required fix:** Change to: "EntityInstance type mismatch (e.g., non-provider instance used as session `provider_instance_id`)."

---

### ISSUE 007-02 [OPEN · MINOR] — Implementation Details in Spec (Library Prescription, Directory Layout)

**Criterion:** B — Agent Actionability
**Location:** SPEC-007 Section 12 (directory layout), Section 13.5 (test factory), Section 3.3 (`cachetools.TTLCache`)

Prescribing specific libraries and directory structures creates unnecessary coupling. An agent using a different caching library with identical behavior would "violate" the spec.

**Required fix:**
- Section 3.3: Replace `cachetools.TTLCache` and "10,000 entry maximum" with: "The cache implementation must be thread-safe, support TTL-based expiration, and have a bounded maximum size to prevent unbounded memory growth. Recommended: 10,000 entry maximum."
- Sections 12 and 13.5–13.6: Add note: "Sections 12 and 13.5–13.6 are reference implementations, not normative requirements. Agents may deviate from the directory structure and factory patterns provided they satisfy the behavioral contracts in all other sections."

---

### ISSUE 007-03 [FIXED] — Missing `GET /entity-types/{slug}/attributes` in Endpoint Inventory

**Criterion:** C — Cross-Spec Integrity
**Status:** Fixed in SPEC-007 v0.2.0. Endpoint added to Section 8.2.

---

### ISSUE 007-04 [OPEN · MAJOR] — Missing CPT/ICD Code Management Endpoints in Inventory

**Criterion:** C — Cross-Spec Integrity
**Location:** SPEC-007 Section 8.6 (only GET endpoints listed)
**Depends on:** ISSUE 002-04

Once write endpoints are added to SPEC-005, they must also appear in SPEC-007's master inventory.

**Required fix:** Add to SPEC-007 Section 8.6:

```
| POST   | /cpt-codes       | Create CPT code for the org | codes.write   |
| PATCH  | /cpt-codes/{id}  | Update a CPT code           | codes.write   |
| DELETE | /cpt-codes/{id}  | Deactivate a CPT code       | codes.delete  |
| POST   | /icd-codes       | Create ICD code for the org | codes.write   |
| PATCH  | /icd-codes/{id}  | Update an ICD code          | codes.write   |
| DELETE | /icd-codes/{id}  | Deactivate an ICD code      | codes.delete  |
```

---

### ISSUE 007-05 [OPEN · MAJOR] — Field-Level Request Body Schemas Missing from Sub-Specs

**Criterion:** E — Definition of Done
**Location:** SPEC-007 Section 8; multiple sub-spec API Surface sections

Sub-specs define table shapes and permissions but not explicit request body schemas for POST/PATCH endpoints. Most mappings can be inferred from table definitions, but several require explicit definition because table structure alone is misleading.

**Ambiguous endpoints requiring explicit schemas (unresolved):**
- `POST /people/{id}/roles` — entity_instance_id rules are complex
- `POST /entities/{type_slug}/{id}/consents` — consent_type_id + lifecycle field interactions
- `POST /documents` — two-step upload: metadata vs file handle, presigned URL return

*(ISSUE 003-05, ISSUE 004-03, and ISSUE 005-03 address the other ambiguous cases.)*

**Required fix:**
1. Add to SPEC-007 Section 8: "Schema authority: The endpoint inventory defines paths, methods, and permissions. Request and response field-level schemas are defined in their owning sub-spec's API Surface section. Where a sub-spec does not define an explicit request body schema, agents should derive the schema from the table definition, treating server-generated columns (id, created_at, updated_at, deleted_at, organization_id, status defaults) as excluded from request bodies."
2. Add explicit request body schemas for the three unresolved endpoints listed above in their respective specs (SPEC-002, SPEC-006).

---

### ISSUE 007-06 [OPEN · MINOR] — No Explicit RBAC Rationale for AppointmentType Delete

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-007 Section 8.4, `DELETE /appointment-types/{id}` uses `settings.write`

`settings.write` covers appointment type deletion and all other org settings. No rationale for this bundling is given, creating ambiguity for anyone designing a future permission refactor.

**Required fix:** Add design note in SPEC-003 Section 6:

> **Permission note:** AppointmentType management uses `settings.write` because appointment types are organizational configuration, not clinical data. This is intentional — only users with administrative access to organization settings should create or modify appointment types. Billers who need appointment type changes must request them through a practice admin.

---

## Cross-Spec Issues

### XSPEC-01 [OPEN · MINOR] — Session → Note → Invoice Data Chain Not Documented

**Criterion:** C — Cross-Spec Integrity

Notes are optional for invoicing, but no spec explicitly states this. An agent may add an unintended "note required before invoice" constraint.

**Required fix:** Add to SPEC-005 Section 4, Business Rules:

> Note independence: Invoice creation does not require a ClinicalNote to exist for the session. Notes and invoices are independent downstream records of a completed session. A session may have an invoice without a note, a note without an invoice, or both.

---

### XSPEC-02 [OPEN · MAJOR] — EAV Endpoints Missing PHI Audit Filter Specification

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-001 Section 7; AttributeValue.value may contain PHI

SPEC-001 mandates AuditLog entries for all EAV changes but does not specify which fields are excluded from snapshots. AttributeValue content could contain PHI stored via custom fields.

**Required fix:** Add to SPEC-001 Section 7, Implementation Constraints:

> Audit PHI filtering for EAV: AuditLog `previous_state` and `next_state` snapshots for AttributeValue changes must exclude the `value` field entirely. The snapshot records which `entity_attribute_id` was changed but not the old or new value. The AuditLog entry records the EntityInstance ID, the EntityAttribute ID, and the action (created/updated/deleted) but never the `AttributeValue.value` content.

---

### XSPEC-03 [OPEN · MAJOR] — Row-Level Filtering Implementation Not Specified Per Domain

**Criterion:** D — RBAC & Compliance
**Location:** SPEC-002 Section 6; SPEC-003, SPEC-004, SPEC-005 API Surface sections

SPEC-002 defines five row-level condition types (`own_clients`, `own_sessions`, `own_notes`, `own_profile`, null). No domain spec (except SPEC-001) references how they are applied at query level.

**Required fix:**
- SPEC-003: Addressed in ISSUE 003-04
- SPEC-004: Addressed in ISSUE 004-04
- SPEC-005: Add to Section 6, Implementation Constraints — "Row-level filtering: Billing endpoints have no row-level conditions in MVP. All billing permissions use null conditions, meaning unrestricted access within the organization for any user holding the permission. Provider roles do not receive billing permissions, so no own_* filtering is needed in this domain."

---

### XSPEC-04 [OPEN · CRITICAL] — Ambiguous POST/PATCH Endpoints Lack Explicit Request Body Schemas

**Criterion:** E — Definition of Done

Six endpoints require judgment calls that the specs do not resolve. Three are addressed by ISSUE 003-05, 004-03, and 005-03. Three remain:
- `POST /people/{id}/roles` — entity_instance_id rules are complex (addressed in ISSUE 007-05)
- `POST /entities/{type_slug}/{id}/consents` — consent_type_id + lifecycle fields
- `POST /documents` — two-step upload pattern

**Required fix:** Add explicit request body schemas for the remaining three endpoints in their owning spec's API Surface section. See ISSUE 007-05 for the schema authority note that covers straightforward inference cases.

---

## Issue Summary by Spec

| Spec | Critical | Major | Minor | Open | Fixed |
|---|---|---|---|---|---|
| SPEC-000 | 0 | 3 | 2 | 5 | 0 |
| SPEC-001 | 1 | 2 | 1 | 4 | 0 |
| SPEC-002 | 1 | 5 | 1 | 7 | 0 |
| SPEC-003 | 1 | 4 | 0 | 5 | 0 |
| SPEC-004 | 1 | 2 | 2 | 5 | 0 |
| SPEC-005 | 0 | 3 | 2 | 5 | 0 |
| SPEC-006 | 0 | 2 | 3 | 5 | 0 |
| SPEC-007 | 0 | 2 | 3 | 5 | 1 |
| Cross-Spec | 1 | 2 | 1 | 4 | 0 |
| **Total** | **5** | **25** | **15** | **45** | **1** |

---

## Priority Work Queue

Work through this table in order. Check off each row when complete.

| # | Done | Issue ID | Spec(s) Affected | Severity | Description | Effort |
|---|---|---|---|---|---|---|
| **— TIER 1: CRITICAL —** |
| 1 | ☐ | 001-01 | SPEC-001 | Critical | Add Test Table (19 test cases) | L |
| 2 | ☐ | 002-01 | SPEC-002 | Critical | Add Test Table (23 test cases) | L |
| 3 | ☐ | 003-03 | SPEC-003 | Critical | Add `is_intake` to AppointmentType; rewrite intake status gate — **do this before #4 to avoid stale test table** | M |
| 4 | ☐ | 003-01 | SPEC-003 | Critical | Add Test Table (29 test cases) | L |
| 5 | ☐ | 004-01 | SPEC-004 | Critical | Remove `amendment_pending → cosigned` lifecycle transition | S |
| 6 | ☐ | XSPEC-04 | SPEC-002/006 | Critical | Add explicit request body schemas for 3 remaining ambiguous endpoints (role assignment, consent creation, document upload) | M |
| **— TIER 2: MAJOR — Cross-Spec Conflicts First —** |
| 7 | ☐ | 002-06 | SPEC-002 | Major | Replace /auth/me response shape to match SPEC-007 multi-org structure | M |
| 8 | ☐ | 002-02 | SPEC-002 | Major | Change `GET /permissions` required permission from `permissions.read` to `roles.read` | S |
| 9 | ☐ | 002-07 | SPEC-000 | Major | Add "SPEC-002 is authoritative" note to personas table | S |
| 10 | ☐ | 000-05 | SPEC-000 | Major | Add permission shorthand disclaimer to personas table | S |
| 11 | ☐ | 000-01 | SPEC-000 | Major | Fix Client row: split `emergency_contact` into `emergency_contact_name, emergency_contact_phone` | S |
| 12 | ☐ | 000-03 | SPEC-001 | Major | Add `dea_number` to Provider seed attributes | S |
| **— TIER 2: MAJOR — Permissions and Endpoints —** |
| 13 | ☐ | 002-04 | SPEC-002 | Major | Add `codes.write` and `codes.delete` to seed permissions; grant to admin and biller roles | M |
| 14 | ☐ | 007-04 | SPEC-005/007 | Major | Add CPT/ICD write/delete endpoints to SPEC-005 Section 5 and SPEC-007 Section 8.6 — **do after #13** | M |
| 15 | ☐ | 002-05 | SPEC-002 | Major | Grant `entity_types.read` to `provider` and `receptionist` roles | S |
| **— TIER 2: MAJOR — Business Rule Precision —** |
| 16 | ☐ | 001-03 | SPEC-001 | Major | Add AttributeValue Type Casting Rules table | M |
| 17 | ☐ | 001-04 | SPEC-001 | Major | Add EntityType slug change cascade rules | M |
| 18 | ☐ | 003-02 | SPEC-003 | Major | Replace non-deterministic duration constraint with `override_duration` flag | S |
| 19 | ☐ | 003-04 | SPEC-003 | Major | Add row-level filtering constraint for session endpoints | S |
| 20 | ☐ | 003-05 | SPEC-003 | Major | Add POST /sessions and PATCH /sessions request/response schemas | L |
| 21 | ☐ | 004-03 | SPEC-004 | Major | Add POST /note/amend request body schema with server-side append format | M |
| 22 | ☐ | 004-04 | SPEC-004 | Major | Add row-level filtering constraint for notes endpoints | S |
| 23 | ☐ | 005-01 | SPEC-005 | Major | Add soft delete restriction business rule for invoices | S |
| 24 | ☐ | 005-02 | SPEC-005 | Major | Fix `partial` status ambiguity in line item lock rule | S |
| 25 | ☐ | 005-03 | SPEC-005 | Major | Add POST /invoices request body schema | M |
| 26 | ☐ | 006-02 | SPEC-006 | Major | Define FormTemplate schema JSONB structure with validation rules | M |
| 27 | ☐ | 006-03 | SPEC-006 | Major | Add error handling spec for `expire_consents` task (per-record transactions) | S |
| 28 | ☐ | XSPEC-02 | SPEC-001 | Major | Add EAV audit PHI filtering rule (exclude AttributeValue.value from snapshots) | S |
| 29 | ☐ | XSPEC-03 | SPEC-005 | Major | Add billing row-level filtering null-conditions note | S |
| 30 | ☐ | 007-02 | SPEC-007 | Major | Remove library prescription; mark Sections 12 and 13.5–13.6 non-normative | M |
| 31 | ☐ | 007-05 | SPEC-007 | Major | Add Schema authority note to Section 8 | S |
| **— TIER 3: MINOR —** |
| 32 | ☐ | 000-02 | SPEC-001 | Minor | Update ADR-001 row table count from 24 to 26 | S |
| 33 | ☐ | 000-04 | SPEC-000 | Minor | Add HIPAA-ready acceptance checklist | M |
| 34 | ☐ | 001-02 | SPEC-001 | Minor | Add AttributeValue timestamp design note (intentional omission) | S |
| 35 | ☐ | 002-03 | SPEC-002 | Minor | Add design note for intentional omission of `notes.delete` | S |
| 36 | ☐ | 004-02 | SPEC-004 | Minor | Add `test_soft_delete_amendment_pending_note_returns_409` to test table | S |
| 37 | ☐ | 004-05 | SPEC-002 | Minor | Add design note for practice_admin notes access boundary | S |
| 38 | ☐ | 005-04 | SPEC-005 | Minor | Add insurance_payer_id validation business rule | S |
| 39 | ☐ | 005-05 | SPEC-002 | Minor | Add design note for `payments.void` bundled with `payments.record` | S |
| 40 | ☐ | 006-01 | SPEC-006 | Minor | Add `pending → revoked` semantic disambiguation design note | S |
| 41 | ☐ | 006-04 | SPEC-006 | Minor | Replace ADR-009 TBD with concrete presigned URL expiry values (15/60 min) | S |
| 42 | ☐ | 006-05 | SPEC-006 | Minor | Define valid enum values for `DocumentType.linked_resource_table` | S |
| 43 | ☐ | 007-01 | SPEC-007 | Minor | Fix stale "conductor" in `bridge_rule_violation` description | S |
| 44 | ☐ | 007-06 | SPEC-003 | Minor | Add design note for AppointmentType delete RBAC intent | S |
| 45 | ☐ | XSPEC-01 | SPEC-005 | Minor | Add note independence business rule (notes not required for invoicing) | S |
| 46 | ✓ | 007-03 | SPEC-007 | — | `GET /entity-types/{slug}/attributes` added to endpoint inventory | FIXED |

---

## Work Session Guide

**Quick wins (S-effort, ~5 min each):** #5, #8, #9, #10, #11, #12, #15, #18, #19, #22, #23, #24, #27, #28, #29, #31, #32, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45 — 25 issues, roughly one afternoon.

**Recommended batches:**

- **Batch A — Test Tables (issues #1, #2, #4):** All follow the same format. Complete #3 first (adds `is_intake` field that #4's test table depends on). ~2–3 hours.
- **Batch B — Cross-spec alignment (issues #7–15):** Touches SPEC-000, SPEC-001, SPEC-002, SPEC-005, SPEC-007 in a single pass. Most are S-effort. ~1 hour.
- **Batch C — Request body schemas (issues #20, #21, #25, #6):** Each endpoint schema is self-contained. Work one at a time. ~2–3 hours.
- **Batch D — Business rule precision (issues #16, #17, #18, #23, #24, #26, #27):** One sitting per spec. ~1 hour per spec.

**Hard dependencies (must be in order):**
- #3 before #4 (AppointmentType `is_intake` field must exist before writing the test case for it)
- #13 before #14 (permissions must be defined before endpoints referencing them are added to SPEC-007)
- #5 before any further SPEC-004 test table work (corrected lifecycle must be reflected in tests)
