# SPEC-REVIEW.md — Autonomous Agent Readiness Audit

**Date:** 2026-04-15
**Reviewer:** Claude Opus 4.6 (Expert Software Architect)
**Scope:** SPEC-000 through SPEC-007
**Purpose:** Ensure every specification is deterministic, unambiguous, and machine-actionable for autonomous agentic development.

---

## Review Criteria

| # | Criterion | Question Answered |
|---|---|---|
| 1 | Master Alignment | Does each sub-spec strictly adhere to SPEC-000 architecture? |
| 2 | Agent Actionability | Can an agent implement every requirement without human interpretation? |
| 3 | Cross-Spec Integrity | Do data flows across specs form a consistent, gap-free chain? |
| 4 | RBAC & Compliance | Does every endpoint have explicit RBAC and audit coverage? |
| 5 | Definition of Done | Does every feature have exact inputs/outputs for deterministic test generation? |

---

## SPEC-000: Platform Overview

### ISSUE 000-01 — Master Alignment: Emergency Contact Field Name Mismatch

**Location:** SPEC-000 Section 1, Personas table, Client row, "Key profile fields" column.

**Problem:** SPEC-000 lists `emergency_contact` as a single field. SPEC-001 Section 3 seed data defines two separate EntityAttributes: `emergency_contact_name` (text, not required) and `emergency_contact_phone` (text, not required). An agent reading SPEC-000 will create a single EAV attribute; an agent reading SPEC-001 will create two. These are contradictory instructions.

**Required Fix:** In SPEC-000 Section 1, Personas table, Client row, change:
```
Key profile fields: intake_status, referral_source, emergency_contact, onboarded_at
```
To:
```
Key profile fields: intake_status, referral_source, emergency_contact_name, emergency_contact_phone, onboarded_at
```

---

### ISSUE 000-02 — Master Alignment: Stale Table Count (24 vs 26)

**Location:** SPEC-000 Section 3, header says "MVP table inventory (26 tables)". SPEC-001 Section 8, ADR-001 row says "Defines the 24-table inventory."

**Problem:** SPEC-000 v1.1.0 added DocumentType and ConsentType, bringing the count to 26. SPEC-001's ADR reference still says 24. An agent tasked with validating completeness will flag a discrepancy.

**Required Fix:** In SPEC-001 Section 8, ADR-001 row, change:
```
Defines the 24-table inventory and EAV + concrete hybrid decision.
```
To:
```
Defines the 26-table inventory and EAV + concrete hybrid decision.
```

---

### ISSUE 000-03 — Agent Actionability: DEA Number Missing from Provider Seed Attributes

**Location:** SPEC-000 Section 1, Personas table, Prescriber row lists `dea_number` as a key profile field. SPEC-001 Section 3, Provider EntityAttributes seed data does not include `dea_number`.

**Problem:** An agent implementing SPEC-001 seed data will not create the `dea_number` attribute. An agent implementing the Prescriber persona from SPEC-000 will expect it to exist. This is a contradiction between the master architecture and the EAV seed specification.

**Required Fix:** In SPEC-001 Section 3, Provider EntityAttributes table, add a row:
```
| dea_number | DEA Number | text | false |
```

---

### ISSUE 000-04 — Agent Actionability: "HIPAA-ready" is Non-Deterministic

**Location:** SPEC-000 Section 6, title "HIPAA-ready design (MVP)".

**Problem:** "HIPAA-ready" has no deterministic definition. An agent cannot verify whether the system meets "HIPAA-ready" criteria without a concrete checklist. The section lists six bullet points but does not state what constitutes passing or failing.

**Required Fix:** Add a verification checklist after the bullet points:
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

## SPEC-001: EAV Data Platform

### ISSUE 001-01 — Definition of Done: Missing Test Table

**Location:** SPEC-001, no test table section exists.

**Problem:** SPEC-004, SPEC-005, and SPEC-006 all include a test table mapping every business rule to named test cases with type and validation target. SPEC-001 defines 5+ business rules (BR-05, multi-tenancy isolation, bridge rule validation, system type protection, required field enforcement) but provides no test mapping. An agent cannot generate deterministic tests without this.

**Required Fix:** Add a new Section 8.5 "Test Table" to SPEC-001 with the following content:

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

### ISSUE 001-02 — Agent Actionability: AttributeValue Lacks Timestamps

**Location:** SPEC-001 Section 2, AttributeValue table definition.

**Problem:** AttributeValue has no `created_at` or `updated_at` columns. Every other table in the system has timestamps. An agent implementing the audit service cannot determine when a value was last modified without querying AuditLog. This is not explicitly stated as a design decision, so an agent may add timestamps (creating a schema drift) or omit them (creating an inconsistency with other tables).

**Required Fix:** Add a design note after the AttributeValue table:
```
**Design note:** AttributeValue intentionally omits created_at, updated_at, and deleted_at.
Value changes are tracked exclusively through AuditLog entries on the parent EntityInstance.
Values are overwritten in place. To delete a value, set it to null. There is no soft-delete
mechanism on individual values.
```

---

### ISSUE 001-03 — Agent Actionability: "Cast by field_type at app layer" is Vague

**Location:** SPEC-001 Section 2, AttributeValue table, `value` column description: "Stored as text, cast by field_type at app layer. See ADR-005."

**Problem:** An agent needs to know the exact casting rules for each field_type to implement the Pydantic validation. ADR-005 is listed as "Pending" and may not exist. The agent has no deterministic mapping from field_type enum values to Python types or validation rules.

**Required Fix:** Add a type casting table to SPEC-001 Section 2, after the AttributeValue definition:
```
### AttributeValue Type Casting Rules

| field_type | Storage format (text) | Python type after cast | Validation rule |
|---|---|---|---|
| text | Raw string | str | Max length 10,000 characters. |
| number | Decimal string (e.g., "123.45") | Decimal | Must parse as a valid decimal. No NaN or Infinity. |
| date | ISO 8601 date (e.g., "2026-04-15") | date | Must parse as YYYY-MM-DD. |
| bool | "true" or "false" (lowercase) | bool | Must be exactly "true" or "false". |
| enum | One of the values in EntityAttribute.options | str | Must be a member of the options array. |
| fk | UUID string | UUID | Must be a valid UUID referencing an EntityInstance of the type specified in EntityAttribute.options. |
| jsonb | JSON string | dict | Must parse as valid JSON. Max size 100KB. |
```

---

### ISSUE 001-04 — Cross-Spec Integrity: EntityType Slug Change Cascading Impact Undefined

**Location:** SPEC-001 Section 6, EntityType management, PATCH note: "When a PATCH changes a custom type's slug, the request must use the old slug in the path."

**Problem:** Changing an EntityType slug has cascading implications: (1) dynamically-generated Permission slugs (SPEC-002 ADR-004) reference the old slug, (2) any row-level condition referencing the old slug becomes invalid, (3) URL routing for `/entities/{type_slug}` changes. None of these cascading effects are specified. An agent implementing the PATCH endpoint has no instructions for maintaining referential integrity.

**Required Fix:** Replace the PATCH note with:
```
**Slug change rules:** When a PATCH changes a custom type's slug:
1. The request path uses the old slug.
2. The system must update all Permission rows where resource_slug equals the old slug
   to use the new slug. Permission.slug is recomputed as {new_slug}.{action}.
3. RolePermission.conditions values referencing the old slug are not automatically updated
   (conditions reference resource types, not slugs). No conditions in MVP reference type
   slugs directly.
4. System types (is_system_type = true) cannot have their slug changed. Return HTTP 409
   with error code `resource_locked`.
```

---

## SPEC-002: Identity and RBAC

### ISSUE 002-01 — Definition of Done: Missing Test Table

**Location:** SPEC-002, no test table section exists.

**Problem:** SPEC-002 defines 9+ business rules with no test mapping. An agent cannot generate deterministic tests.

**Required Fix:** Add a "Test Table" section to SPEC-002:

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

### ISSUE 002-02 — Cross-Spec Integrity: `permissions.read` Referenced but Undefined

**Location:** SPEC-002 Section 8, `GET /permissions` requires `permissions.read`. SPEC-007 Section 8.3 lists the same endpoint requiring `roles.read`.

**Problem:** `permissions.read` does not exist in the seed permissions list (SPEC-002 Section 3). An agent seeding the database will not create this permission. An agent implementing the `GET /permissions` endpoint using SPEC-002 will configure a permission check that always fails for all users.

**Required Fix:** In SPEC-002 Section 8, Role and permission management table, change:
```
| GET | /permissions | List available permissions | permissions.read |
```
To:
```
| GET | /permissions | List available permissions | roles.read |
```

---

### ISSUE 002-03 — RBAC & Compliance: No `notes.delete` Permission

**Location:** SPEC-002 Section 3 seed permissions. SPEC-004 Section 7, `DELETE /sessions/{session_id}/note` requires `notes.write`.

**Problem:** Every other domain with soft-delete endpoints uses a dedicated `.delete` permission (clients.delete, documents.delete, people.delete, entity_types.delete). Notes are the sole exception, using `notes.write` for deletion. An agent implementing permission checks will either (a) create notes.delete by analogy and break the spec, or (b) use notes.write and create a permission model inconsistency.

**Required Fix:** Add a design note to SPEC-002 Section 3, after the seed permissions table:
```
**Design note on notes.delete:** A dedicated notes.delete permission is intentionally omitted.
Only draft notes may be soft-deleted (BR-05), and only the author may delete their own drafts.
The notes.write permission covers this action because draft deletion is semantically equivalent
to discarding an unfinished edit, not destroying a clinical record.
```

---

### ISSUE 002-04 — Cross-Spec Integrity: No CPT/ICD Code Management Permissions or Endpoints

**Location:** SPEC-002 Section 3 defines only `codes.read`. SPEC-005 Section 5 defines only `GET` endpoints for CPT/ICD codes. CPTCode and ICDCode tables have `is_active` flags and are organization-scoped.

**Problem:** There is no way for any user to create, update, or deactivate CPT/ICD codes through the API. The tables exist with org-scoping and active flags, implying CRUD management is needed, but no endpoints or permissions exist. An agent implementing billing cannot populate the code tables.

**Required Fix:** Add to SPEC-002 Section 3 seed permissions:
```
| codes.write | codes | write | Create or update CPT and ICD reference codes. |
| codes.delete | codes | delete | Deactivate CPT and ICD reference codes. |
```

Add `codes.write` and `codes.delete` as direct grants to `admin` and `biller` in the seed matrix.

Add to SPEC-005 Section 5, Reference code management:
```
| POST | /cpt-codes | Create a CPT code for the org | codes.write |
| PATCH | /cpt-codes/{id} | Update a CPT code | codes.write |
| DELETE | /cpt-codes/{id} | Deactivate a CPT code (set is_active = false) | codes.delete |
| POST | /icd-codes | Create an ICD code for the org | codes.write |
| PATCH | /icd-codes/{id} | Update an ICD code | codes.write |
| DELETE | /icd-codes/{id} | Deactivate an ICD code (set is_active = false) | codes.delete |
```

Add corresponding rows to SPEC-007 Section 8.6.

---

### ISSUE 002-05 — RBAC & Compliance: `entity_types.read` Not Granted to Providers

**Location:** SPEC-002 Section 3 seed matrix. `entity_types.read` is granted only to `admin` (inherited by practice_admin, system_admin).

**Problem:** Providers need to know what entity types exist to understand their profile structure and the types of clients and colleagues in the system. The EAV instance endpoints (`GET /entities/{type_slug}`) require `{type_slug}.read`, but discovering available type slugs requires `entity_types.read`, which providers lack. An agent building a provider-facing UI will fail to populate entity type dropdowns.

**Required Fix:** In SPEC-002 Section 3 seed matrix, add `entity_types.read` as a direct grant to the `provider` role (which will be inherited by therapist, supervisor, prescriber). Also grant to `receptionist` (who manages client intake and needs to know entity types).

---

### ISSUE 002-06 — Cross-Spec Integrity: /auth/me Response Shape Conflict

**Location:** SPEC-002 Section 8 defines a flat response with single `organization` object and `effective_permissions` array. SPEC-007 Section 3.4 defines a nested response with `organizations[]` array containing per-org role arrays.

**Problem:** Two specs define incompatible JSON response shapes for the same endpoint. An agent implementing this endpoint must choose one and will violate the other.

**Required Fix:** SPEC-007's multi-org array structure is correct because `GET /auth/me` does not require `X-Organization-Id` and must return all organizations. Replace SPEC-002 Section 8, `/auth/me response shape` with:
```
### /auth/me response shape

The response matches SPEC-007 Section 3.4. It includes person identity and all organizations
with their roles. No effective_permissions field is included — use GET /auth/me/permissions
with X-Organization-Id for the resolved permission set.

| Field | Type | Description |
|---|---|---|
| person.id | UUID | Person primary key. |
| person.first_name | String | First name. |
| person.last_name | String | Last name. |
| person.email | String | Email address. |
| organizations | Array | All orgs where the person has active roles. |
| organizations[].id | UUID | Organization primary key. |
| organizations[].name | String | Practice name. |
| organizations[].roles | Array | Active PersonRole records in this org. |
| organizations[].roles[].role_slug | String | Role machine identifier. |
| organizations[].roles[].role_name | String | Role display name. |
| organizations[].roles[].primary_domain | Enum | admin, provider, or client. |
| organizations[].roles[].entity_instance_id | UUID, nullable | Bound profile instance. |
```

---

## SPEC-003: Scheduling and Sessions

### ISSUE 003-01 — Definition of Done: Missing Test Table

**Location:** SPEC-003, no test table section exists.

**Problem:** SPEC-003 defines 9+ business rules and scheduling constraints with no test mapping.

**Required Fix:** Add a "Test Table" section to SPEC-003:

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

### ISSUE 003-02 — Agent Actionability: "Shorter durations allowed only if explicitly set" is Non-Deterministic

**Location:** SPEC-003 Section 5, Scheduling Constraints: "Shorter durations are allowed only if explicitly set by a user with sessions.write permission."

**Problem:** Every session creation requires `sessions.write` permission, so this clause provides no actual constraint. An agent cannot determine the difference between an "explicitly set" shorter duration and any other submitted duration. Two agents would implement this differently.

**Required Fix:** Replace the constraint with:
```
End-to-end duration consistency: The difference between end_time and start_time must equal
or exceed the AppointmentType's default_duration_minutes. If the submitted duration is shorter
than the default, the request must include `override_duration: true` in the request body.
Requests with a shorter duration that omit this flag are rejected with HTTP 422,
error code `validation_error`, detail: "Session duration is shorter than the appointment type
default. Set override_duration to true to confirm."
```

---

### ISSUE 003-03 — Agent Actionability: "Non-Intake Session Type" is Undefined

**Location:** SPEC-003 Section 5, Scheduling Constraints: "A client must have an EntityInstance with intake_status of complete or in_progress before a non-intake session type can be scheduled for them."

**Problem:** AppointmentType has no field distinguishing "intake" from "non-intake" types. The `name` field is free-form text. An agent cannot deterministically classify an AppointmentType as intake or non-intake.

**Required Fix:** Add a field to AppointmentType in SPEC-003 Section 2:
```
| is_intake | Boolean | NOT NULL, default false | When true, this type can be scheduled for clients regardless of intake_status. |
```

Then rewrite the constraint:
```
Intake status gate: A client with intake_status = "new" may only be scheduled for
AppointmentTypes where is_intake = true. Clients with intake_status = "in_progress" or
"complete" may be scheduled for any active AppointmentType. Requests violating this rule
are rejected with HTTP 422, error code `prerequisite_not_met`,
message: "Client intake_status must be 'in_progress' or 'complete' for non-intake appointment types."
```

---

### ISSUE 003-04 — RBAC & Compliance: Row-Level Filtering Not Specified for Session Endpoints

**Location:** SPEC-003 Section 6 API Surface. SPEC-002 Section 6 defines `scope: own_sessions` condition for provider roles.

**Problem:** SPEC-003 lists `sessions.read` and `sessions.write` as permissions but does not specify how row-level conditions from SPEC-002 are applied. An agent implementing `GET /sessions` for a therapist does not know whether to filter by `provider_instance_id = requesting user's instance` or return all sessions in the org. SPEC-002 defines the condition semantics but SPEC-003 does not reference them.

**Required Fix:** Add to SPEC-003 Section 7, Implementation Constraints:
```
- Row-level filtering: When the requesting user's RolePermission grant for sessions.read or
  sessions.write includes conditions {"scope": "own_sessions"}, the query must filter
  Session records to only those where provider_instance_id matches the requesting user's
  EntityInstance ID (resolved from their active PersonRole). Null conditions mean unrestricted
  access within the organization. See SPEC-002 Section 6.
```

---

### ISSUE 003-05 — Definition of Done: Session Create/Update Request Schema Not Defined

**Location:** SPEC-003 Section 6, `POST /sessions` and `PATCH /sessions/{id}`.

**Problem:** No request body schema is defined. An agent cannot generate a Pydantic model without knowing the exact fields, which are required vs optional, and what the response shape looks like.

**Required Fix:** Add to SPEC-003 Section 6:
```
### POST /sessions request body

| Field | Type | Required | Description |
|---|---|---|---|
| appointment_type_id | UUID | Yes | Must reference an active AppointmentType in the same org. |
| provider_instance_id | UUID | Yes | Must reference an EntityInstance of type provider in the same org. |
| client_instance_id | UUID | Yes | Must reference an EntityInstance of type client in the same org. |
| start_time | Timestamp (ISO 8601 UTC) | Yes | Session start time. |
| end_time | Timestamp (ISO 8601 UTC) | Yes | Session end time. Must be after start_time. |
| location | String | No | Physical address or telehealth identifier. |
| notes | String | No | Internal scheduling notes. Max 2000 characters. |

### PATCH /sessions/{id} request body

All fields optional. Only provided fields are updated. Status cannot be changed via PATCH;
use the explicit transition endpoints. provider_instance_id and client_instance_id cannot
be changed after creation; return HTTP 409, error code `resource_locked` if attempted.

### Session response body

| Field | Type | Description |
|---|---|---|
| id | UUID | Session primary key. |
| organization_id | UUID | Tenant. |
| appointment_type_id | UUID | Template reference. |
| provider_instance_id | UUID | Provider profile. |
| client_instance_id | UUID | Client profile. |
| start_time | Timestamp | ISO 8601 UTC. |
| end_time | Timestamp | ISO 8601 UTC. |
| status | String | Current lifecycle status. |
| cancellation_reason | String, nullable | Set on cancel/no-show. |
| cancelled_at | Timestamp, nullable | When cancelled. |
| cancelled_by_person_id | UUID, nullable | Who cancelled. |
| location | String, nullable | Location. |
| notes | String, nullable | Scheduling notes. |
| created_at | Timestamp | Creation time. |
| updated_at | Timestamp | Last modification. |
```

---

## SPEC-004: Clinical Notes

### ISSUE 004-01 — Agent Actionability: Lifecycle Contradiction (amendment_pending -> cosigned)

**Location:** SPEC-004 Section 4, Note Status Lifecycle table shows `amendment_pending -> cosigned` as a valid transition. Section 6, Amendment Model step 4 says "the author re-signs the note."

**Problem:** The lifecycle table allows a co-signer to directly co-sign an amended note without the author re-signing first. The amendment model in Section 6 requires re-signing before co-signing. These are contradictory. An agent implementing the lifecycle will allow a path that the amendment model forbids.

**Required Fix:** In SPEC-004 Section 4, lifecycle table, remove the `amendment_pending -> cosigned` row:
```
Remove:
| amendment_pending | cosigned | Any person with notes.cosign permission co-signs amended note |

The corrected lifecycle for amendment_pending is:
| amendment_pending | signed | Author (notes.sign permission) re-signs after amendment |
```

Add a note: "An amended note must be re-signed by the author before it can be co-signed. The path is always: amendment_pending -> signed -> cosigned."

---

### ISSUE 004-02 — Definition of Done: Missing Test for amendment_pending Soft Delete

**Location:** SPEC-004 Section 10, Test Table.

**Problem:** Tests exist for `test_soft_delete_signed_note_returns_409` and `test_soft_delete_cosigned_note_returns_409` but not for `amendment_pending`. BR-05 states "only draft ClinicalNotes may be soft-deleted." Amendment_pending is not draft, so deletion must be blocked.

**Required Fix:** Add to SPEC-004 Section 10 test table:
```
| ClinicalNote | `deleted_at` | `test_soft_delete_amendment_pending_note_returns_409` | Integration | Amendment_pending notes protected from deletion |
```

---

### ISSUE 004-03 — Agent Actionability: Amendment Append Semantics Undefined at API Level

**Location:** SPEC-004 Section 6: "Each cycle appends to amendment_note rather than replacing it." Section 7, `POST /sessions/{session_id}/note/amend`.

**Problem:** The amend endpoint has no request body schema. An agent does not know: (1) what field name the amendment text is submitted under, (2) what separator is used between multiple amendments, (3) whether the append happens server-side or the client must send the full concatenated text.

**Required Fix:** Add to SPEC-004 Section 7, after the lifecycle transitions table:
```
### POST /sessions/{session_id}/note/amend request body

| Field | Type | Required | Description |
|---|---|---|---|
| amendment_text | String | Yes | The addendum text. Min 1 character, max 10000 characters. |

The backend appends the amendment_text to the existing amendment_note field using the
following format:

    [AMENDMENT {ISO 8601 UTC timestamp} by {person first_name last_name}]\n{amendment_text}\n\n

The client never sends the full amendment_note. The backend always appends. If the client
sends a request body that includes an `amendment_note` field (attempting to overwrite),
return HTTP 422, error code `validation_error`,
message: "amendment_note cannot be set directly. Use amendment_text."
```

---

### ISSUE 004-04 — RBAC & Compliance: Row-Level Filtering for Notes Not Specified in SPEC-004

**Location:** SPEC-004 Section 7 API Surface. SPEC-002 Section 6 defines `scope: own_notes` for provider roles.

**Problem:** SPEC-004 does not specify how `scope: own_notes` is applied to `GET /notes` or `GET /sessions/{session_id}/note`. An agent implementing the notes list endpoint for a therapist role does not know whether to filter by `author_instance_id`.

**Required Fix:** Add to SPEC-004 Section 8, Implementation Constraints:
```
- Row-level filtering: When the requesting user's RolePermission grant for notes.read
  includes conditions {"scope": "own_notes"}, the query must filter ClinicalNote records
  to only those where author_instance_id matches the requesting user's EntityInstance ID.
  Null conditions mean unrestricted access within the organization. See SPEC-002 Section 6.
```

---

## SPEC-005: Billing and Payments

### ISSUE 005-01 — Agent Actionability: Invoice Soft Delete vs Void Relationship Unclear

**Location:** SPEC-005 Section 2, Invoice has both `deleted_at` and `status = void`. Section 4 Business Rules, Section 8 Test Table.

**Problem:** The test table includes `test_soft_delete_draft_invoice_succeeds`, implying only draft invoices can be soft-deleted. But the business rules section never explicitly states this restriction. An agent reading only the business rules will not know which statuses allow soft-delete. The void and soft-delete mechanisms overlap without a clear delineation.

**Required Fix:** Add to SPEC-005 Section 4, Business Rules:
```
- Soft delete restriction: Only invoices in draft status may be soft-deleted via
  DELETE /invoices/{id}. Invoices in sent, partial, paid, or void status must not be
  soft-deleted. To remove a non-draft invoice from active use, void it via
  POST /invoices/{id}/void. Attempts to soft-delete a non-draft invoice return HTTP 409,
  error code `state_transition_denied`,
  message: "Only draft invoices may be deleted. Use the void endpoint for non-draft invoices."
```

---

### ISSUE 005-02 — Agent Actionability: "Partial" Status Ambiguity in Line Item Lock Rule

**Location:** SPEC-005 Section 4: "Line items cannot be added, updated, or deleted on an invoice in paid or void status. Only draft and sent invoices allow line item modification."

**Problem:** The first sentence excludes paid and void. The second sentence allows only draft and sent. The `partial` status falls through the cracks. The first sentence does not block it, but the second sentence does not allow it. An agent reading the first sentence may allow edits on partial invoices.

**Required Fix:** Replace both sentences with:
```
- Locked invoice editing: Line items can only be added, updated, or deleted on invoices
  in draft or sent status. Invoices in partial, paid, or void status are locked.
  Attempts to modify line items on a locked invoice return HTTP 409,
  error code `resource_locked`,
  message: "Line items cannot be modified on invoices in {status} status."
```

---

### ISSUE 005-03 — Definition of Done: Invoice Create Request Schema Missing

**Location:** SPEC-005 Section 5, `POST /invoices`.

**Problem:** No request body schema is defined. The business rules state that `client_instance_id` and `provider_instance_id` are "derived from the session, not accepted as independent input." An agent does not know what the request body contains.

**Required Fix:** Add to SPEC-005 Section 5:
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

### ISSUE 005-04 — Cross-Spec Integrity: Payment `insurance_payer_id` Validation Not in Business Rules

**Location:** SPEC-005 Section 8 test table includes `test_insurance_payment_without_payer_id_returns_422`. Section 4 Business Rules does not state this rule.

**Problem:** The test table defines a test for a rule that is not in the business rules section. An agent writing the service layer from the business rules will not implement this validation. An agent writing tests from the test table will create a test for non-existent logic.

**Required Fix:** Add to SPEC-005 Section 4, Business Rules:
```
- Insurance payer required: When Payment.payer_type is "insurance",
  insurance_payer_id must be non-null and reference an active InsurancePayer in the same org.
  When payer_type is "client" or "other", insurance_payer_id must be null.
  Violations return HTTP 422, error code `validation_error`.
```

---

### ISSUE 005-05 — RBAC & Compliance: No `payments.void` Permission

**Location:** SPEC-002 Section 3 seed permissions. SPEC-005 Section 5, `POST /invoices/{id}/payments/{payment_id}/void` requires `payments.record`.

**Problem:** Voiding a payment is a destructive action that reverses financial records. Using `payments.record` (intended for recording new payments) for voiding creates a privilege conflation. A biller who can record payments can also void them without a distinct permission check. An agent implementing fine-grained access control cannot separate these actions.

**Required Fix:** Either add `payments.void` to SPEC-002 seed permissions and update SPEC-005's void endpoint to require it, OR add a design note in SPEC-002 Section 3:
```
**Design note on payments.void:** A dedicated payments.void permission is intentionally omitted.
Payment voiding is bundled with payments.record because the void-and-rerecord workflow
is a single logical operation. All payment voids are tracked in AuditLog with the void reason,
providing an audit trail without requiring a separate permission gate.
```

---

## SPEC-006: Documents, Consent, and Compliance

### ISSUE 006-01 — Agent Actionability: "pending -> revoked" Consent Transition Semantics

**Location:** SPEC-006 Section 3, Consent Status Lifecycle: `pending -> revoked` is allowed.

**Problem:** "Revoked" implies withdrawal of previously-granted consent. Revoking a consent that was never signed is semantically different (it's a decline, not a revocation). An agent implementing a consent audit report cannot distinguish between "client withdrew signed consent" and "client declined to sign" because both end in `revoked` status.

**Required Fix:** Add to SPEC-006 Section 3, after the lifecycle table:
```
**Design note:** The `revoked` terminal status covers both declined-before-signing and
withdrawn-after-signing cases. The distinction is deterministic from the data:
- If signed_at IS NULL and status = revoked: consent was declined before signing.
- If signed_at IS NOT NULL and status = revoked: consent was withdrawn after signing.
Agents and reports should use this distinction rather than relying on status alone.
```

---

### ISSUE 006-02 — Agent Actionability: FormTemplate Schema JSONB Structure Undefined

**Location:** SPEC-006 Section 2, FormTemplate.schema: "JSONB. Form field definitions. Describes field names, types, labels, and required flags."

**Problem:** An agent cannot implement Pydantic validation for FormTemplate.schema without knowing the exact structure. This is the same problem SPEC-004 solved by defining exact content schemas for SOAP/DAP/BIRP formats.

**Required Fix:** Add to SPEC-006 Section 2, after the FormTemplate table:
```
### FormTemplate Schema Structure

The `schema` JSONB field must conform to this structure:

{
  "fields": [
    {
      "name": "string (required, machine name, [a-z_]+)",
      "label": "string (required, human-readable display label)",
      "type": "string (required, one of: text, textarea, number, date, boolean, select, multiselect, email, phone)",
      "required": "boolean (required, default false)",
      "options": ["array of strings (required when type is select or multiselect, null otherwise)"],
      "placeholder": "string (optional, hint text for form input)",
      "max_length": "integer (optional, max character length for text/textarea)",
      "validation_regex": "string (optional, regex pattern for custom validation)"
    }
  ]
}

Validation rules:
- The fields array must contain at least one field.
- Field names must be unique within the array.
- Field names must match the regex [a-z][a-z0-9_]{0,63}.
- Select and multiselect types must have a non-empty options array.
- Non-select types must have options = null.
```

---

### ISSUE 006-03 — Agent Actionability: Consent Expiry Task Error Handling Unspecified

**Location:** SPEC-006 Section 3, `expire_consents` Celery Beat task.

**Problem:** The task processes multiple consent records in batch. The spec does not define what happens if one record fails to transition (e.g., database error on one row). An agent implementing the task must decide between: (a) atomic batch (all or nothing), (b) individual transactions (skip failures), (c) stop on first error. Each has different correctness implications.

**Required Fix:** Add to SPEC-006 Section 3, after the expire_consents description:
```
Error handling: Each consent record is expired in its own database transaction. A failure
on one record (e.g., constraint violation, database error) is logged at ERROR level and
does not prevent processing of remaining records. Failed records are retried on the next
scheduled run. The task reports the total count of successfully expired records and the
count of failures in its Celery result.
```

---

### ISSUE 006-04 — RBAC & Compliance: Presigned URL Expiry Window Not Specified

**Location:** SPEC-006 Section 7: "S3 presigned download URLs must have a short expiry. The exact window is defined in ADR-009 but must be measured in minutes, not hours."

**Problem:** ADR-009 is listed as "Pending" and may not exist. An agent implementing the presigned URL generation has no concrete expiry value. "Measured in minutes" is a range from 1 to 59 with very different security implications.

**Required Fix:** Replace the constraint with:
```
- Presigned URL expiry: S3 presigned download URLs expire after 15 minutes.
  S3 presigned upload URLs expire after 60 minutes. These defaults may be overridden
  by ADR-009 when finalized. Until ADR-009 is accepted, use these values.
```

---

## SPEC-007: API Contract and Testing

### ISSUE 007-01 — Agent Actionability: Stale "conductor" Reference

**Location:** SPEC-007 Section 7.3, `bridge_rule_violation` error code description: "non-provider as session conductor."

**Problem:** "Conductor" was renamed to "provider" in SPEC-003 v0.2.0 and SPEC-005 v0.3.0. An agent reading this error description will use the wrong terminology in error messages.

**Required Fix:** Change:
```
| 422 | `bridge_rule_violation` | EntityInstance type mismatch (e.g., non-provider as session conductor) |
```
To:
```
| 422 | `bridge_rule_violation` | EntityInstance type mismatch (e.g., non-provider instance used as session provider_instance_id) |
```

---

### ISSUE 007-02 — Agent Actionability: Implementation Details in Spec (Directory Layout, Library Prescriptions)

**Location:** SPEC-007 Section 12 (Application Structure), Section 13.5 (Test Factory example), Section 3.3 (`cachetools.TTLCache` and 10,000 entry maximum).

**Problem:** These are implementation decisions, not behavioral contracts. An agent should be told *what* the system must do, not *how* to organize files. Prescribing a specific library creates unnecessary coupling. If an agent chooses a different caching library with identical behavior, the spec would be "violated" despite correct behavior.

**Required Fix:**
1. In Section 3.3, replace:
```
The cache implementation must use a thread-safe LRU cache with TTL (e.g., cachetools.TTLCache). Maximum cache size is 10,000 entries.
```
With:
```
The cache implementation must be thread-safe, support TTL-based expiration, and have a bounded
maximum size to prevent unbounded memory growth. Recommended: 10,000 entry maximum.
```

2. Sections 12 and 13.5-13.6 should be marked as non-normative:
```
**Note:** Sections 12 and 13.5-13.6 are reference implementations, not normative
requirements. Agents may deviate from the directory structure and factory patterns
as long as they satisfy the behavioral contracts in all other sections.
```

---

### ISSUE 007-03 — Cross-Spec Integrity: Missing `GET /entity-types/{slug}/attributes` in Endpoint Inventory

**Location:** SPEC-007 Section 8.2. SPEC-001 Section 6 defines `GET /entity-types/{slug}/attributes`.

**Problem:** SPEC-007 omits this endpoint from the master inventory. An agent generating the OpenAPI spec from SPEC-007 will miss this endpoint. An agent implementing SPEC-001 will create it, creating an undocumented endpoint.

**Required Fix:** Add to SPEC-007 Section 8.2, EAV Platform table:
```
| GET | /entity-types/{slug}/attributes | List attributes for a type | entity_types.read |
```

---

### ISSUE 007-04 — Cross-Spec Integrity: Missing CPT/ICD Code Management Endpoints in Inventory

**Location:** SPEC-007 Section 8.6. Only `GET /cpt-codes` and `GET /icd-codes` are listed.

**Problem:** Per ISSUE 002-04, write endpoints for CPT/ICD codes need to be added. SPEC-007 must reflect these additions.

**Required Fix:** Add to SPEC-007 Section 8.6:
```
| POST | /cpt-codes | Create CPT code | codes.write |
| PATCH | /cpt-codes/{id} | Update CPT code | codes.write |
| DELETE | /cpt-codes/{id} | Deactivate CPT code | codes.delete |
| POST | /icd-codes | Create ICD code | codes.write |
| PATCH | /icd-codes/{id} | Update ICD code | codes.write |
| DELETE | /icd-codes/{id} | Deactivate ICD code | codes.delete |
```

---

### ISSUE 007-05 — Definition of Done: Field-Level Request Body Schemas Missing from Sub-Specs

**Location:** SPEC-007 Section 8 (endpoint inventory) and sub-spec API Surface sections.

**What the specs DO define well:** The API contract layer is substantial. SPEC-007 defines routing conventions (`/api/v1/` prefix), authentication flow (Auth0 JWT + `X-Organization-Id` header), the standard error envelope with machine-readable error codes, cursor-based pagination with response envelope, timestamp/UUID/money formatting, and Pydantic-everywhere mandates. Each sub-spec defines endpoints with method, path, description, and required permission. This is a solid contract for routing, middleware, and error handling.

**What is missing:** Field-level request body schemas for POST and PATCH endpoints. The specs define *what tables look like* (column names, types, constraints) and *what the API routes are*, but not the explicit mapping between the two. An agent can infer ~80% of a request schema by reading the table definition and business rules — e.g., `POST /sessions` likely accepts most Session columns minus server-generated fields like `id`, `status`, `created_at`. But some mappings require judgment calls that the specs don't resolve:

- Which table columns are client-supplied vs server-derived? (e.g., Invoice's `client_instance_id` is derived from the session, per SPEC-005 business rules, but this is stated in prose, not in a schema)
- Which fields are required on create vs optional on update?
- Are there request-only fields not on the table? (e.g., `override_duration` for sessions)
- What are the max lengths, format constraints, and validation rules beyond column types?

SPEC-004 is the exception — it explicitly defines SOAP/DAP/BIRP content schemas with required keys, making it fully agent-actionable.

**Required Fix:** Each sub-spec should add explicit request body schemas for its POST and PATCH endpoints, distinguishing client-supplied fields from server-derived fields. This does not need to live in SPEC-007 — each sub-spec owns its schemas. Add a note to SPEC-007 Section 8:
```
**Schema authority:** The endpoint inventory defines paths, methods, and permissions.
Request and response field-level schemas are defined in their owning sub-spec's API Surface
section. Both this inventory and the sub-spec must agree on path, method, and permission.
Field-level schemas are authoritative only in the sub-spec. Where a sub-spec does not
define an explicit request body schema, agents should derive the schema from the table
definition, treating server-generated columns (id, created_at, updated_at, deleted_at,
organization_id, status defaults) as excluded from request bodies.
```

---

### ISSUE 007-06 — RBAC & Compliance: No Explicit RBAC for AppointmentType Delete

**Location:** SPEC-007 Section 8.4 lists `DELETE /appointment-types/{id}` requiring `settings.write`. SPEC-003 Section 6 also lists `settings.write`.

**Problem:** AppointmentType deletion uses the generic `settings.write` permission. This means anyone who can update organization settings can also deactivate appointment types. This is a permission overload. More importantly, `settings.write` is only granted to the `admin` role (and children), but billers may need to manage appointment types for billing code alignment. The permission model conflates two distinct capabilities.

**Required Fix:** Add a design note in SPEC-003 Section 6:
```
**Permission note:** AppointmentType management uses settings.write because appointment types
are organization configuration, not clinical data. This is intentional — only users with
administrative access to organization settings should create or modify appointment types.
Billers who need appointment type changes must request them through a practice admin.
```

---

## Cross-Spec Findings

### XSPEC-01 — Cross-Spec Integrity: Session -> Note -> Invoice Data Chain Validation

**Problem:** The chain Session (SPEC-003) -> ClinicalNote (SPEC-004) -> Invoice (SPEC-005) is the core business flow, but no spec validates the full chain end-to-end. Specifically:
- SPEC-004 requires session status `in_progress` or `completed` for note creation.
- SPEC-005 requires session status `completed` for invoice creation.
- Neither spec verifies that a note exists before invoicing (notes are optional for billing).

This is not a bug — notes should be optional for invoicing. But this design decision should be explicit.

**Required Fix:** Add to SPEC-005 Section 4, Business Rules:
```
- Note independence: Invoice creation does not require a ClinicalNote to exist for the session.
  Notes and invoices are independent downstream records of a completed session.
  A session may have an invoice without a note, a note without an invoice, or both.
```

---

### XSPEC-02 — RBAC & Compliance: SPEC-001 EAV Endpoints Missing Audit Log Specification

**Location:** SPEC-001 Section 7 mentions "Every state-changing API call on EAV tables must generate a record in AuditLog per BR-07." SPEC-006 Section 5 Audit Coverage Matrix lists EAV actions.

**Problem:** SPEC-001 does not specify which fields are included in audit log `previous_state` and `next_state` snapshots, or which fields are excluded as PHI per BR-08. AttributeValue content could contain PHI (e.g., diagnosis information stored as a custom field). An agent implementing the audit service for EAV changes has no guidance on PHI filtering.

**Required Fix:** Add to SPEC-001 Section 7, Implementation Constraints:
```
- Audit PHI filtering for EAV: AuditLog previous_state and next_state snapshots for
  AttributeValue changes must exclude the `value` field entirely. The snapshot records
  which entity_attribute_id was changed but not the old or new value. This ensures no
  practice-specific PHI leaks into the audit trail. The AuditLog entry records the
  EntityInstance ID, the EntityAttribute ID, and the action (created/updated/deleted)
  but never the AttributeValue.value content.
```

---

### XSPEC-03 — RBAC & Compliance: Row-Level Filtering Implementation Not Specified Per Domain

**Problem:** SPEC-002 Section 6 defines five row-level condition types (`own_clients`, `own_sessions`, `own_notes`, `own_profile`, `null`). The condition semantics are defined in SPEC-002, but the actual query-level enforcement must happen in each domain's service layer. Only SPEC-001 Section 7.3 references this integration contract. SPEC-003, SPEC-004, and SPEC-005 do not reference row-level filtering at all, despite having endpoints that are affected by it.

**Required Fix:** Each domain spec that has endpoints affected by row-level conditions must add an implementation constraint. Required additions:

SPEC-003 (addressed in ISSUE 003-04 above).

SPEC-004 (addressed in ISSUE 004-04 above).

SPEC-005, add to Section 6, Implementation Constraints:
```
- Row-level filtering: Billing endpoints do not have row-level conditions in MVP.
  All billing permissions (invoices.*, payments.*, insurance.*, codes.*) use null conditions,
  meaning unrestricted access within the organization for any user holding the permission.
  Provider roles do not receive billing permissions, so no own_* filtering is needed.
```

---

### XSPEC-04 — Definition of Done: Field-Level Request Body Schemas Not Explicit in Most Sub-Specs

**Context:** The specs define a strong API contract layer — routing, authentication, error handling, pagination, permissions, and data model schemas are all well-specified. The gap is narrower than "no API contract": it is specifically that most sub-specs do not provide explicit request body schemas for POST/PATCH endpoints, leaving agents to infer them from table definitions and business rules.

**Why this matters for autonomous agents:** An experienced developer can read a table definition and business rules to derive a reasonable request schema. An autonomous agent can do the same for straightforward cases (e.g., `POST /insurance-payers` maps closely to the InsurancePayer table minus server-generated fields). But edge cases require human judgment that the specs don't codify:

- `POST /invoices` — business rules say `client_instance_id` and `provider_instance_id` are derived from the session. An agent reading only the Invoice table definition would include them in the request body.
- `POST /sessions/{session_id}/note/amend` — the table has `amendment_note` but the request should accept `amendment_text` (a different field) with server-side append logic.
- `PATCH /sessions/{id}` — can `provider_instance_id` be changed after creation? The table allows it; the business logic may not.

**Endpoints where inference is straightforward** (table columns minus server fields):
- `POST /insurance-payers`, `POST /cpt-codes`, `POST /icd-codes`
- `POST /document-types`, `POST /consent-types`
- `POST /form-templates` (except the schema JSONB — see ISSUE 006-02)

**Endpoints where inference is ambiguous** (require explicit schemas):
- `POST /sessions` (SPEC-003 — addressed in ISSUE 003-05)
- `POST /invoices` (SPEC-005 — addressed in ISSUE 005-03)
- `POST /sessions/{session_id}/note/amend` (SPEC-004 — addressed in ISSUE 004-03)
- `POST /people/{id}/roles` (entity_instance_id rules are complex)
- `POST /entities/{type_slug}/{id}/consents` (consent_type_id + lifecycle fields)
- `POST /documents` (two-step upload pattern, metadata vs file)

**Required Fix:** Prioritize adding explicit request body schemas for the ambiguous endpoints listed above. For straightforward endpoints, add a derivation rule to SPEC-007 (see ISSUE 007-05) so agents know how to infer schemas from table definitions. At minimum, each ambiguous endpoint schema must include: field name, type, required flag, and whether the field is client-supplied or server-derived.

---

## Summary

### Issue Counts by Spec

| Spec | Critical | Major | Minor | Total |
|---|---|---|---|---|
| SPEC-000 | 0 | 2 | 2 | 4 |
| SPEC-001 | 1 | 2 | 1 | 4 |
| SPEC-002 | 1 | 4 | 1 | 6 |
| SPEC-003 | 1 | 3 | 1 | 5 |
| SPEC-004 | 1 | 2 | 1 | 4 |
| SPEC-005 | 0 | 3 | 2 | 5 |
| SPEC-006 | 0 | 2 | 2 | 4 |
| SPEC-007 | 0 | 3 | 3 | 6 |
| Cross-Spec | 1 | 3 | 0 | 4 |
| **Total** | **5** | **24** | **13** | **42** |

### Critical Issues (Block Autonomous Implementation)

| ID | Issue | Blocking Because |
|---|---|---|
| 001-01 | SPEC-001 missing test table | Agent cannot generate deterministic tests for EAV layer |
| 002-01 | SPEC-002 missing test table | Agent cannot generate deterministic tests for RBAC layer |
| 003-01 | SPEC-003 missing test table | Agent cannot generate deterministic tests for scheduling |
| 004-01 | Lifecycle contradiction (amendment_pending -> cosigned) | Agent will implement mutually exclusive state transitions |
| XSPEC-04 | Ambiguous POST/PATCH endpoints lack explicit request body schemas | Agent must make judgment calls on client-supplied vs server-derived fields |

### Priority Order for Fixes

1. **Add missing test tables** to SPEC-001, SPEC-002, SPEC-003 (issues 001-01, 002-01, 003-01)
2. **Fix lifecycle contradiction** in SPEC-004 (issue 004-01)
3. **Add explicit request body schemas** for ambiguous endpoints + derivation rule for straightforward ones (XSPEC-04, 003-05, 005-03)
4. **Fix cross-spec conflicts** (/auth/me shape, permissions.read, path parameters) (002-02, 002-06, 007-03)
5. **Add missing permissions and endpoints** for CPT/ICD codes (002-04, 007-04)
6. **Resolve all ambiguous language** (003-02, 003-03, 005-01, 005-02, 006-01, 006-02, 006-03)
7. **Add row-level filtering references** to domain specs (003-04, 004-04, XSPEC-03)
8. **Add RBAC design notes** for intentional bundling (002-03, 005-05, 007-06)
