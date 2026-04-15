# SPEC Review — Issue Digest

**Date:** 2026-04-15
**Total:** 46 issues (45 open, 1 fixed)

---

## Quick Resolve (no design decision needed — clear, mechanical fix)

| # | ID | Spec | Severity | Issue |
|---|---|---|---|---|
| 1 | 000-01 | SPEC-000 | Major | `emergency_contact` in persona table doesn't match SPEC-001 seed data (`emergency_contact_name` + `emergency_contact_phone`) |
| 2 | 000-02 | SPEC-000/001 | Minor | SPEC-001 ADR-001 says "24 tables" but SPEC-000 says 26 |
| 3 | 001-02 | SPEC-001 | Minor | AttributeValue has no timestamps, and no design note explaining the intentional omission |
| 4 | 002-02 | SPEC-002/007 | Major | `permissions.read` required for `GET /permissions` but never defined as a seed permission — SPEC-007 already uses `roles.read` |
| 5 | 002-06 | SPEC-002/007 | Major | `/auth/me` response shape conflicts — SPEC-002 has flat single-org, SPEC-007 has nested multi-org array |
| 6 | 002-07 | SPEC-000/002 | Major | Two competing role-permission representations (SPEC-000 personas table vs SPEC-002 seed matrix) with no stated authority |
| 7 | 004-01 | SPEC-004 | **Critical** | Lifecycle table allows `amendment_pending -> cosigned` but amendment model requires re-signing first |
| 8 | 004-02 | SPEC-004 | Minor | Missing test for `test_soft_delete_amendment_pending_note_returns_409` |
| 9 | 005-02 | SPEC-005 | Major | Line item lock rule contradicts itself — first sentence allows `partial`, second sentence blocks it |
| 10 | 005-04 | SPEC-005 | Minor | Test table tests `insurance_payer_id` required when `payer_type=insurance` but no business rule states this |
| 11 | 007-01 | SPEC-007 | Minor | Stale "conductor" terminology in `bridge_rule_violation` error description |
| 12 | 007-03 | SPEC-007 | — | `GET /entity-types/{slug}/attributes` missing from endpoint inventory — **already fixed in v0.2.0** |
| 13 | XSPEC-01 | Cross-spec | Minor | No spec explicitly states that notes are optional for invoicing |

---

## Requires Consideration (design decision, product input, or judgment call needed)

| # | ID | Spec | Severity | Issue | Decision Needed |
|---|---|---|---|---|---|
| 1 | 000-03 | SPEC-000/001 | Major | `dea_number` listed for Prescriber persona but never seeded in SPEC-001 provider attributes | Is `dea_number` a provider-level attribute or prescriber-specific? |
| 2 | 000-04 | SPEC-000 | Minor | "HIPAA-ready" has no concrete acceptance checklist | What are the actual MVP pass/fail criteria? |
| 3 | 000-05 | SPEC-000 | Major | Permission shorthand in personas table (`clients.rw`, `invoices.*`) doesn't match actual seed permission slugs | Remove shorthand, add disclaimer, or rewrite column? |
| 4 | 001-01 | SPEC-001 | **Critical** | No test table — 5+ business rules with no test case mapping | Review and approve proposed test cases before they become spec |
| 5 | 001-03 | SPEC-001 | Major | No type casting rules for `field_type` enum — just "cast at app layer" and ADR-005 is pending | What are the max lengths, decimal precision, JSONB size limits? |
| 6 | 001-04 | SPEC-001 | Major | EntityType slug rename has undefined cascading effects on permissions and routing | Allow slug renames at all, or block them? |
| 7 | 002-01 | SPEC-002 | **Critical** | No test table — 9+ business rules with no test case mapping | Review and approve proposed test cases |
| 8 | 002-03 | SPEC-002 | Minor | No `notes.delete` permission — notes are the only domain using `.write` for deletion | Intentional bundling, or add a separate permission? |
| 9 | 002-04 | SPEC-002/005 | Major | No permissions or API endpoints for CPT/ICD code management, but tables have `is_active` flags | Managed through API, seed data, or separate admin tool? |
| 10 | 002-05 | SPEC-002 | Major | `entity_types.read` not granted to providers — they can't discover available type slugs | Broadly grant to providers and receptionists, or handle through implicit access? |
| 11 | 003-01 | SPEC-003 | **Critical** | No test table — 9+ business rules with no test case mapping | Review and approve proposed test cases |
| 12 | 003-02 | SPEC-003 | Major | "Shorter durations allowed only if explicitly set by a user with sessions.write" — meaningless since all session creators have that permission | Add concrete override mechanism, or drop the rule and enforce minimum duration? |
| 13 | 003-03 | SPEC-003 | Major | "Non-intake session type" referenced but AppointmentType has no `is_intake` field | Add the field, define classification differently, or remove the constraint? |
| 14 | 003-04 | SPEC-003 | Major | Row-level filtering (`own_sessions`) defined in SPEC-002 but never referenced in SPEC-003 | Each domain spec repeats enforcement rules, or single cross-reference? |
| 15 | 003-05 | SPEC-003 | Major | `POST /sessions` has no request body schema — which fields are required vs optional is ambiguous | Which fields are client-supplied vs server-derived? |
| 16 | 004-03 | SPEC-004 | Major | Amendment endpoint has no request body schema — field name, append format, and client vs server responsibility undefined | What field name, separator format, and append behavior? |
| 17 | 004-04 | SPEC-004 | Major | Row-level filtering (`own_notes`) defined in SPEC-002 but never referenced in SPEC-004 | Same decision as 003-04 |
| 18 | 004-05 | SPEC-004 | Minor | `practice_admin` lacks `notes.write`/`notes.sign` — whether they can participate in amendment workflows is unstated | Intentional exclusion, or should practice admins have limited notes access? |
| 19 | 005-01 | SPEC-005 | Major | Invoice has both `deleted_at` and `status=void` — relationship between the two never stated | Only drafts can be soft-deleted? Any non-terminal? |
| 20 | 005-03 | SPEC-005 | Major | `POST /invoices` has no request body schema — `client_instance_id` and `provider_instance_id` are server-derived but only stated in prose | Confirm which fields are accepted vs derived |
| 21 | 005-05 | SPEC-005 | Minor | No `payments.void` permission — voiding uses `payments.record` | Intentional bundling, or separate permission? |
| 22 | 006-01 | SPEC-006 | Minor | `pending -> revoked` consent transition is semantically odd (decline vs withdrawal) | Add a `declined` status, or keep `revoked` for both with disambiguation rule? |
| 23 | 006-02 | SPEC-006 | Major | FormTemplate `schema` JSONB has no defined structure | What field types do your forms actually need? |
| 24 | 006-03 | SPEC-006 | Major | `expire_consents` Celery task has no error handling defined (batch vs individual transactions) | Per-record transactions, atomic batch, or stop on first error? |
| 25 | 006-04 | SPEC-006 | Minor | Presigned URL expiry deferred to pending ADR-009 — no concrete default value | Pick a number (15 min download / 60 min upload is reasonable) |
| 26 | 006-05 | SPEC-006 | Minor | `DocumentType.linked_resource_table` is a free-form string with no valid values defined | What are the allowed table names? |
| 27 | 007-02 | SPEC-007 | Minor | Directory layout and `cachetools.TTLCache` are implementation details in the spec | Keep as non-normative guidance, or move out entirely? |
| 28 | 007-04 | SPEC-007 | Major | CPT/ICD code write endpoints missing from master endpoint inventory | Depends on decision for 002-04 |
| 29 | 007-05 | SPEC-007 | Major | Sub-specs don't have explicit request body schemas — most inferable from tables, but ambiguous cases exist | Add schemas for ambiguous endpoints, add derivation rule, or both? |
| 30 | 007-06 | SPEC-007 | Minor | `settings.write` overloaded for AppointmentType management | Intentional, or add dedicated permission? |
| 31 | XSPEC-02 | Cross-spec | Major | EAV audit log has no guidance on PHI filtering for AttributeValue content | Always exclude values from snapshots, or only for attributes flagged as PHI? |
| 32 | XSPEC-03 | Cross-spec | **Critical** | Row-level filtering conditions defined in SPEC-002 but SPEC-003, 004, 005 never reference how to apply them | Same decision as 003-04 — systemic |
| 33 | XSPEC-04 | Cross-spec | Major | ~6 ambiguous endpoints need explicit request body schemas | Confirm client-supplied vs server-derived fields per endpoint |
