# Groundwork Specification Suite — Review Report

**Date:** 2026-04-08
**Reviewer:** Claude Opus 4.6
**Specs reviewed:** SPEC-000 through SPEC-007 (including SPEC-006-erd)

---

## Per-Spec Findings

---

### SPEC-000: Platform Overview

**Spec:** SPEC-000-platform-overview
**Section:** §1 Personas table — Key profile fields
**Check:** Naming consistency
**Issue:** Client persona lists `emergency_contact` as a single field, but SPEC-001 seed data defines `emergency_contact_name` and `emergency_contact_phone` as separate EntityAttributes.
**Suggested fix:** Update SPEC-000 persona table to list `emergency_contact_name, emergency_contact_phone` to match SPEC-001.

**Spec:** SPEC-000-platform-overview
**Section:** §8 ADR index / §3 Data model overview
**Check:** Clarity & Ambiguity
**Issue:** SPEC-001 §8 refers to "24-table inventory" in ADR-001 description, but the current SPEC-000 §3 table inventory lists 26 tables (added in v1.1.0). The stale count in SPEC-001 could mislead developers.
**Suggested fix:** Update SPEC-001 ADR-001 row to say "26-table inventory" or "MVP table inventory."

---

### SPEC-001: EAV Data Platform

**Spec:** SPEC-001-eav-data-platform
**Section:** §2 AttributeValue
**Check:** Completeness
**Issue:** AttributeValue has no `created_at`, `updated_at`, or `deleted_at` columns. If a value is changed, there's no record of when. If a value needs soft deletion, there's no mechanism. Other tables in the spec all have timestamps.
**Suggested fix:** Either add `created_at`/`updated_at` to AttributeValue or document explicitly that value history is tracked only via AuditLog and that values are overwritten in place.

**Spec:** SPEC-001-eav-data-platform
**Section:** Full spec
**Check:** Completeness
**Issue:** No test table section. SPEC-004, SPEC-005, and SPEC-006 all include a test table mapping every business rule to test cases. SPEC-001 has 5+ business rules (BR-05, multi-tenancy, bridge rule, system type protection, required field enforcement) with no test mapping.
**Suggested fix:** Add a test table section consistent with SPEC-004/005/006 format.

**Spec:** SPEC-001-eav-data-platform
**Section:** §6 API Surface — EntityType management
**Check:** API contract coverage / Naming consistency
**Issue:** SPEC-001 uses `{id}` as path parameter for entity types (`/entity-types/{id}`) and `{type_id}` for attributes (`/entity-types/{type_id}/attributes`). SPEC-007 §8.2 uses `{slug}` for entity types (`/entity-types/{slug}`) and `{slug}` for attributes (`/entity-types/{slug}/attributes/{attr_id}`). These are incompatible.
**Suggested fix:** Align on one approach. Since slugs are unique per org and URL-safe, `{slug}` is likely the better choice. Update SPEC-001 to match SPEC-007.

**Spec:** SPEC-001-eav-data-platform
**Section:** §6 API Surface — EntityAttribute management
**Check:** API contract coverage
**Issue:** SPEC-001 defines `GET /entity-types/{type_id}/attributes` (list attributes), but SPEC-007 §8.2 omits this endpoint — it only lists POST, PATCH, DELETE for attributes, not a standalone GET.
**Suggested fix:** Add `GET /entity-types/{slug}/attributes` to SPEC-007 §8.2, or remove it from SPEC-001 if listing is handled by the parent `GET /entity-types/{slug}` response.

---

### SPEC-002: Identity and RBAC

**Spec:** SPEC-002-identity-and-rbac
**Section:** §8 API Surface — Role and permission management
**Check:** RBAC coverage / Naming consistency
**Issue:** `GET /permissions` requires `permissions.read` in SPEC-002's API table, but `permissions.read` does not appear in the seed permissions list (§3). SPEC-007 §8.3 lists the same endpoint as requiring `roles.read`. The permission `permissions.read` is undefined.
**Suggested fix:** Change `GET /permissions` permission to `roles.read` in SPEC-002 to match SPEC-007 and the seed permission set, or add `permissions.read` to the seed list.

**Spec:** SPEC-002-identity-and-rbac
**Section:** Full spec
**Check:** Completeness
**Issue:** No test table section. SPEC-002 defines 8+ business rules (BR-06, role union, tenant isolation, hierarchy invariant, inheritance, assignment integrity, revocation, soft delete, auth subject) with no test mapping.
**Suggested fix:** Add a test table section consistent with SPEC-004/005/006 format.

**Spec:** SPEC-002-identity-and-rbac
**Section:** §3 Seed permissions
**Check:** RBAC coverage
**Issue:** No `notes.delete` permission is defined. SPEC-004 uses `notes.write` for `DELETE /sessions/{session_id}/note`. Every other domain with soft-delete has a dedicated `.delete` permission (clients.delete, documents.delete, people.delete). Notes are the exception.
**Suggested fix:** Either add `notes.delete` to the seed permissions and update SPEC-004 API table, or add a comment in SPEC-002 explaining that note deletion is intentionally covered by `notes.write` (since only draft notes can be deleted).

**Spec:** SPEC-002-identity-and-rbac
**Section:** §3 Seed permissions
**Check:** RBAC coverage
**Issue:** No write or delete permissions exist for CPT/ICD code management (`codes.write`, `codes.delete`). Only `codes.read` is defined. SPEC-005 only defines `GET` endpoints for codes, but organizations need to manage their code tables — there's no mechanism defined for creating, updating, or deactivating CPT/ICD codes.
**Suggested fix:** Either add `codes.write` and `codes.delete` permissions and corresponding API endpoints to SPEC-005, or document that code tables are managed through seed data or a separate admin interface.

**Spec:** SPEC-002-identity-and-rbac
**Section:** §3 Seed role-permission matrix
**Check:** RBAC coverage
**Issue:** The `entity_types.read` permission is granted only to admin (and inherited by practice_admin, system_admin). Providers and receptionists cannot list entity types, even though providers need to know what entity types exist (e.g., to understand their profile structure).
**Suggested fix:** Review whether `entity_types.read` should be broadly granted, or if the EAV endpoints handle this through implicit access.

---

### SPEC-003: Scheduling and Sessions

**Spec:** SPEC-003-scheduling-and-sessions
**Section:** Full spec
**Check:** Completeness
**Issue:** No test table section. SPEC-003 defines 7+ business rules (BR-01, BR-02, BR-03, bridge rules, cancellation reason, AppointmentType guard, consent gate) with no test mapping.
**Suggested fix:** Add a test table section consistent with SPEC-004/005/006 format.

**Spec:** SPEC-003-scheduling-and-sessions
**Section:** §5 Scheduling Constraints — Duration consistency
**Check:** Clarity & Ambiguity
**Issue:** "Shorter durations are allowed only if explicitly set by a user with sessions.write permission" is ambiguous. Every session creation requires `sessions.write`, so this rule adds no real constraint. Two developers could interpret this differently: one might require a separate override flag, another might treat any submitted duration as "explicit."
**Suggested fix:** Either remove the shorter-duration exception (enforce minimum duration from AppointmentType), or define a concrete mechanism (e.g., a boolean `override_duration` field or a separate permission).

**Spec:** SPEC-003-scheduling-and-sessions
**Section:** §5 Scheduling Constraints — Intake status check
**Check:** Completeness
**Issue:** "A client must have an EntityInstance with intake_status of complete or in_progress before a non-intake session type can be scheduled" — there's no definition of what makes an AppointmentType an "intake" type. AppointmentType has no `is_intake` flag or equivalent.
**Suggested fix:** Add an `is_intake` boolean to AppointmentType, or define the rule in terms of AppointmentType name/category, or remove this constraint.

---

### SPEC-004: Clinical Notes

**Spec:** SPEC-004-clinical-notes
**Section:** §4 Note Status Lifecycle
**Check:** Clarity & Ambiguity
**Issue:** The lifecycle table shows `amendment_pending -> cosigned` as a direct transition ("Any person with notes.cosign permission co-signs amended note"), but there's no intermediate `signed` state required. This means an amendment could be co-signed without the author re-signing. The amendment model (§6) says "the author re-signs" as step 4, implying `amendment_pending -> signed -> cosigned`. The lifecycle table contradicts the amendment model.
**Suggested fix:** Remove the `amendment_pending -> cosigned` direct transition from the lifecycle table, requiring the path `amendment_pending -> signed -> cosigned`.

**Spec:** SPEC-004-clinical-notes
**Section:** §10 Test Table
**Check:** Completeness
**Issue:** The test table tests `test_soft_delete_signed_note_returns_409` and `test_soft_delete_cosigned_note_returns_409` but does not test `test_soft_delete_amendment_pending_note_returns_409`. BR-05 says "only draft ClinicalNotes may be soft-deleted" — amendment_pending is not draft.
**Suggested fix:** Add `test_soft_delete_amendment_pending_note_returns_409` to the test table.

**Spec:** SPEC-004-clinical-notes
**Section:** §5 Business Rules — Soft delete rule
**Check:** Clarity & Ambiguity
**Issue:** "Because of the one-note-per-session constraint, a new note cannot replace a soft-deleted one." combined with `UNIQUE(session_id)` including soft-deleted records means a session with a soft-deleted note is permanently blocked from having a new note. This is a strong design choice that should be called out more prominently — a developer might expect soft-delete to free the slot.
**Suggested fix:** This appears intentional (audit trail preservation). Add a brief rationale sentence explaining why: e.g., "This prevents circumventing the audit trail by soft-deleting and re-creating notes."

---

### SPEC-005: Billing and Payments

**Spec:** SPEC-005-billing-and-payments
**Section:** §5 API Surface — Reference code management
**Check:** Completeness
**Issue:** Only `GET` endpoints exist for CPT and ICD codes. There are no endpoints for creating, updating, or deactivating codes. The tables are org-scoped with `is_active` flags, implying they need CRUD management, but no API surface is defined for it.
**Suggested fix:** Add POST, PATCH, and DELETE (deactivate) endpoints for both `/cpt-codes` and `/icd-codes`, define the required permissions (e.g., `codes.write`), and update SPEC-002 and SPEC-007 accordingly.

**Spec:** SPEC-005-billing-and-payments
**Section:** §2 Invoice — deleted_at
**Check:** Clarity & Ambiguity
**Issue:** Invoice has both `deleted_at` (soft delete) and `status = void` as mechanisms for removing an invoice from active use. The relationship between these two mechanisms is not clearly defined. Can a voided invoice also be soft-deleted? Can a non-voided invoice be soft-deleted?
**Suggested fix:** Add a rule clarifying the relationship: e.g., "Only draft invoices may be soft-deleted. Invoices in any other status must be voided, not deleted." (The test table implies this with `test_soft_delete_draft_invoice_succeeds` but the business rules section doesn't state it.)

**Spec:** SPEC-005-billing-and-payments
**Section:** §4 Business Rules — Locked invoice editing
**Check:** Clarity & Ambiguity
**Issue:** The rule first says "Line items cannot be added, updated, or deleted on an invoice in paid or void status" then says "Only draft and sent invoices allow line item modification." The first sentence omits `partial` from the blocked list, while the second sentence implicitly blocks it. A developer reading only the first sentence might allow edits on partial invoices.
**Suggested fix:** Rewrite the first sentence to: "Line items cannot be added, updated, or deleted on an invoice in partial, paid, or void status."

---

### SPEC-006: Documents, Consent, and Compliance

**Spec:** SPEC-006-documents-consent-compliance
**Section:** §3 Consent Status Lifecycle
**Check:** Clarity & Ambiguity
**Issue:** The lifecycle allows `pending -> revoked`. Revoking a consent that was never signed is semantically odd. This is likely intended to handle "client declined to sign" but the term "revoked" implies withdrawal of previously-granted consent.
**Suggested fix:** Either rename the terminal state for declined unsigned consents (e.g., add a `declined` status), or document that `revoked` is used for both declined and withdrawn consents.

**Spec:** SPEC-006-documents-consent-compliance
**Section:** §4 Business Rules — FormTemplate rules
**Check:** Completeness
**Issue:** FormTemplate schema is described as JSONB with "field names, types, labels, and required flags" but there's no schema definition for what this JSONB structure looks like. A developer would have to guess the form field definition format.
**Suggested fix:** Define the FormTemplate schema structure (at minimum: field name, field type, label, required flag, and any validation rules), similar to how SPEC-004 defines note content schemas.

**Spec:** SPEC-006-documents-consent-compliance
**Section:** §3 Consent expiry task
**Check:** Completeness
**Issue:** The consent expiry Celery task `expire_consents` is well-defined, but the spec does not define error handling for the batch operation. If one consent fails to transition, does the task stop, skip, or roll back all?
**Suggested fix:** Add a statement: "Each consent record is expired in its own transaction. A failure on one record does not prevent processing of remaining records. Failed records are logged for retry on the next run."

---

### SPEC-006-erd (Entity Relationship Diagram)

**Spec:** SPEC-006-erd
**Section:** Document entity
**Check:** Data shape consistency
**Issue:** The ERD shows Document with `linked_resource_type` (string) and `is_active` (boolean), but SPEC-006 v0.2.0 replaced this with `document_type_id` FK -> DocumentType (which carries `linked_resource_table`). Document has no `is_active` field in the spec. The ERD is stale.
**Suggested fix:** Update the ERD to show `document_type_id` FK -> DocumentType, remove `linked_resource_type` and `is_active` from Document, and add DocumentType and ConsentType entities.

**Spec:** SPEC-006-erd
**Section:** ClientConsent entity
**Check:** Data shape consistency
**Issue:** The ERD shows `consent_type` as an Enum directly on ClientConsent, but SPEC-006 v0.2.0 replaced this with `consent_type_id` FK -> ConsentType. The ERD also omits `deleted_at` on ClientConsent.
**Suggested fix:** Update ClientConsent in the ERD to use `consent_type_id` FK -> ConsentType and add `deleted_at`.

**Spec:** SPEC-006-erd
**Section:** FormTemplate entity
**Check:** Data shape consistency
**Issue:** The ERD shows `organization_id` as nullable ("null for system templates"), but SPEC-006 defines `organization_id` as NOT NULL ("System templates are seeded per-org on organization creation").
**Suggested fix:** Update the ERD to show `organization_id` as NOT NULL on FormTemplate.

**Spec:** SPEC-006-erd
**Section:** Missing entities
**Check:** Data shape consistency
**Issue:** DocumentType and ConsentType tables are completely absent from the ERD despite being defined in SPEC-006 v0.2.0 and being central to the domain.
**Suggested fix:** Add DocumentType and ConsentType entities to the ERD with their relationships to Document and ClientConsent respectively.

---

### SPEC-007: API Contract and Testing

**Spec:** SPEC-007-api-contract-and-testing
**Section:** §12 Application Structure, §13.5 Test Factories
**Check:** No Implementation Leakage
**Issue:** Section 12 includes a full filesystem directory tree with file-by-file layout. Section 13.5 includes a Python function signature. Section 3.3 prescribes a specific library (`cachetools.TTLCache`) and cache size (10,000 entries). These are implementation decisions, not spec-level contracts.
**Suggested fix:** Move §12 (application structure) and §13.5 (factory example) to an implementation guide or ADR. Replace the `cachetools.TTLCache` reference with a behavioral requirement ("thread-safe TTL cache, 60s TTL, bounded size").

**Spec:** SPEC-007-api-contract-and-testing
**Section:** §7.3 Standard error codes — bridge_rule_violation
**Check:** Naming consistency
**Issue:** The error description says "non-provider as session conductor." The term "conductor" was renamed to "provider" in SPEC-003 v0.2.0 and SPEC-005 v0.3.0. This is a stale reference.
**Suggested fix:** Change to "non-provider as session provider_instance" or "EntityInstance type mismatch on session provider."

**Spec:** SPEC-007-api-contract-and-testing
**Section:** §3.4 /auth/me response
**Check:** Data shape consistency
**Issue:** SPEC-007's /auth/me response shape differs from SPEC-002's. SPEC-002 §8 shows a flat structure with `person`, `organization`, `roles`, `effective_permissions`. SPEC-007 §3.4 shows a nested structure with `person` and `organizations[]` (array with roles nested per org). These are incompatible response shapes.
**Suggested fix:** Align on one shape. SPEC-007's version (multi-org array) is more correct since `GET /auth/me` doesn't require org context and must return all orgs. Update SPEC-002 §8 to match.

**Spec:** SPEC-007-api-contract-and-testing
**Section:** §8.2 EAV Platform endpoint inventory
**Check:** API contract coverage
**Issue:** SPEC-007 omits `GET /entity-types/{slug}/attributes` (list attributes for a type). SPEC-001 defines this endpoint but SPEC-007 only lists POST, PATCH, DELETE for attributes.
**Suggested fix:** Add `GET /entity-types/{slug}/attributes` to the SPEC-007 inventory.

---

## Cross-Spec Findings

---

**Spec:** SPEC-006-erd
**Section:** File naming
**Check:** Duplicate numbering
**Issue:** `SPEC-006-documents-consent-compliance.md` and `SPEC-006-erd.md` share the SPEC-006 number. The ERD is a supplementary diagram, not a separate domain spec, but the naming creates confusion about whether it's an independent spec.
**Suggested fix:** Rename the ERD file to `SPEC-006-appendix-erd.md` or move to `diagrams/SPEC-006-erd.md` to make the supplementary relationship clear.

**Spec:** Cross-spec (SPEC-003 / SPEC-006)
**Section:** Consent gate
**Check:** Dependency direction
**Issue:** SPEC-003 (Scheduling) has a runtime dependency on SPEC-006 (Compliance) for the consent gate check at session completion. SPEC-006 also references SPEC-003 when defining the consent gate semantics. This creates a bidirectional dependency between a lower-numbered and higher-numbered spec.
**Suggested fix:** This is already documented and justified as a service-layer call. No change needed, but consider adding a dependency map diagram to SPEC-000 showing the cross-domain service calls.

**Spec:** Cross-spec (SPEC-002, SPEC-003, SPEC-004, SPEC-005)
**Section:** Permission definitions
**Check:** RBAC coverage — operations without permissions
**Issue:** Several operations across domain specs have no corresponding permission in SPEC-002:
1. CPT/ICD code management — no `codes.write` or `codes.delete` (and no management endpoints exist either)
2. AppointmentType management uses `settings.write` — overloads a generic permission for a specific domain concept
3. Note deletion uses `notes.write` — no `notes.delete` exists
4. Payment voiding uses `payments.record` — no `payments.void` exists
**Suggested fix:** For items 1-2: add dedicated permissions or document the design decision. For items 3-4: either add `notes.delete` and `payments.void`, or add a note in SPEC-002 explaining that these are intentionally bundled.

**Spec:** Cross-spec (SPEC-000, SPEC-001)
**Section:** Persona field naming
**Check:** Naming consistency
**Issue:** SPEC-000 §1 persona table lists `emergency_contact` for Client, but SPEC-001 §3 defines it as two fields: `emergency_contact_name` and `emergency_contact_phone`.
**Suggested fix:** Update SPEC-000 persona table to match SPEC-001 field names exactly.

**Spec:** Cross-spec (SPEC-001, SPEC-007)
**Section:** Entity type path parameters
**Check:** Naming consistency
**Issue:** SPEC-001 uses `{id}` (UUID) for entity type path parameters. SPEC-007 uses `{slug}` (string). These produce different URL shapes and router logic.
**Suggested fix:** Standardize on `{slug}` since EntityType slugs are unique per org and URL-friendly, then update SPEC-001 §6.

**Spec:** Cross-spec (SPEC-002, SPEC-007)
**Section:** /auth/me response shape
**Check:** Data shape consistency
**Issue:** SPEC-002 §8 defines /auth/me with a single `organization` object and flat `roles` array. SPEC-007 §3.4 defines it with an `organizations` array containing per-org role arrays. These are structurally incompatible.
**Suggested fix:** Adopt SPEC-007's multi-org structure (it correctly handles the multi-org use case). Update SPEC-002 §8.

**Spec:** Cross-spec (SPEC-002, SPEC-007)
**Section:** GET /permissions endpoint
**Check:** Naming consistency
**Issue:** SPEC-002 §8 requires `permissions.read` for `GET /permissions`. SPEC-007 §8.3 requires `roles.read` for the same endpoint. `permissions.read` is not a defined seed permission.
**Suggested fix:** Use `roles.read` in both specs (it's defined and semantically correct — "List and view roles and permissions").

---

## Summary Table

| Spec | Completeness | Clarity | No Impl. Leakage | Scope Bleed | Data Shape | RBAC Coverage | API Coverage | Naming | Dependencies |
|---|---|---|---|---|---|---|---|---|---|
| SPEC-000 | Pass | Flag | Pass | Pass | Flag | — | — | Flag | Pass |
| SPEC-001 | Flag | Pass | Pass | Pass | Flag | Pass | Flag | Flag | Pass |
| SPEC-002 | Flag | Pass | Pass | Pass | Pass | Flag | Flag | Flag | Pass |
| SPEC-003 | Flag | Flag | Pass | Pass | Pass | Flag | Pass | Pass | Flag |
| SPEC-004 | Pass | Flag | Pass | Pass | Pass | Flag | Pass | Pass | Pass |
| SPEC-005 | Flag | Flag | Pass | Pass | Pass | Flag | Flag | Pass | Pass |
| SPEC-006 | Pass | Flag | Pass | Pass | Pass | Pass | Pass | Pass | Pass |
| SPEC-006-erd | — | — | — | — | **Fail** | — | — | — | — |
| SPEC-007 | Pass | Flag | **Fail** | Pass | Flag | Flag | Flag | Flag | Pass |

**Legend:** Pass = no issues found. Flag = minor issues that need resolution. Fail = structural problems requiring rework.

---

## Top-Priority Items

1. **SPEC-006-erd is stale** — missing DocumentType/ConsentType, wrong column names on Document and ClientConsent, wrong nullability on FormTemplate. Needs full rework to match SPEC-006 v0.2.0.
2. **SPEC-007 implementation leakage** — directory layout, code examples, and library prescriptions should move to an implementation guide.
3. **SPEC-001/SPEC-007 path parameter mismatch** (`{id}` vs `{slug}`) — blocks consistent router implementation.
4. **SPEC-002/SPEC-007 /auth/me response shape conflict** — two incompatible contracts for the same endpoint.
5. **Missing test tables** in SPEC-001, SPEC-002, SPEC-003 — inconsistent with SPEC-004/005/006 pattern.
6. **Undefined `permissions.read`** — referenced but never created as seed permission.
7. **No CPT/ICD code management endpoints** — tables exist with is_active flags but no API to manage them.
