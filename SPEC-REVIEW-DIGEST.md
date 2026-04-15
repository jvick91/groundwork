# SPEC Review — Issue Digest

**Date:** 2026-04-15

| ID | Spec | Severity | Issue |
|---|---|---|---|
| 000-01 | SPEC-000 | Major | `emergency_contact` in persona table doesn't match SPEC-001 seed data (`emergency_contact_name` + `emergency_contact_phone`) |
| 000-02 | SPEC-000/001 | Minor | SPEC-001 ADR-001 says "24 tables" but SPEC-000 says 26 |
| 000-03 | SPEC-000/001 | Major | `dea_number` listed for Prescriber persona but never seeded in SPEC-001 Provider attributes |
| 000-04 | SPEC-000 | Minor | "HIPAA-ready" has no concrete acceptance checklist |
| 001-01 | SPEC-001 | **Critical** | No test table — 5+ business rules with no test case mapping |
| 001-02 | SPEC-001 | Minor | AttributeValue has no timestamps, and no design note explaining why |
| 001-03 | SPEC-001 | Major | No type casting rules for field_type enum (text, number, date, bool, enum, fk, jsonb) — just "cast at app layer" |
| 001-04 | SPEC-001 | Major | EntityType slug rename has undefined cascading effects on permissions, routing, and conditions |
| 002-01 | SPEC-002 | **Critical** | No test table — 9+ business rules with no test case mapping |
| 002-02 | SPEC-002/007 | Major | `permissions.read` required for `GET /permissions` but never defined as a seed permission |
| 002-03 | SPEC-002 | Minor | No `notes.delete` permission — notes are the only domain using `.write` for deletion with no explanation |
| 002-04 | SPEC-002/005 | Major | No permissions or API endpoints for CPT/ICD code management, but tables have `is_active` flags |
| 002-05 | SPEC-002 | Major | `entity_types.read` not granted to providers — they can't discover available type slugs |
| 002-06 | SPEC-002/007 | Major | `/auth/me` response shape is different in SPEC-002 (flat, single org) vs SPEC-007 (nested, multi-org array) |
| 003-01 | SPEC-003 | **Critical** | No test table — 9+ business rules with no test case mapping |
| 003-02 | SPEC-003 | Major | "Shorter durations allowed only if explicitly set by a user with sessions.write" — every user creating sessions has this permission, so the rule is meaningless |
| 003-03 | SPEC-003 | Major | "Non-intake session type" referenced but AppointmentType has no `is_intake` field |
| 003-04 | SPEC-003 | Major | Row-level filtering (`own_sessions`) defined in SPEC-002 but never referenced in SPEC-003 |
| 003-05 | SPEC-003 | Major | `POST /sessions` has no request body schema — which fields are required vs optional is ambiguous |
| 004-01 | SPEC-004 | **Critical** | Lifecycle table allows `amendment_pending -> cosigned` but amendment model requires re-signing first — contradictory |
| 004-02 | SPEC-004 | Minor | Missing test for `test_soft_delete_amendment_pending_note_returns_409` |
| 004-03 | SPEC-004 | Major | Amendment endpoint has no request body schema — field name, append format, and responsibility (client vs server) undefined |
| 004-04 | SPEC-004 | Major | Row-level filtering (`own_notes`) defined in SPEC-002 but never referenced in SPEC-004 |
| 005-01 | SPEC-005 | Major | Invoice has both `deleted_at` and `status=void` — relationship between the two never stated (only inferable from test table) |
| 005-02 | SPEC-005 | Major | Line item lock rule contradicts itself — first sentence allows `partial`, second sentence blocks it |
| 005-03 | SPEC-005 | Major | `POST /invoices` has no request body schema — `client_instance_id` and `provider_instance_id` are server-derived but only stated in prose |
| 005-04 | SPEC-005 | Major | Test table tests `insurance_payer_id` required when `payer_type=insurance` but no business rule states this |
| 005-05 | SPEC-005 | Minor | No `payments.void` permission — voiding uses `payments.record` with no design note explaining why |
| 006-01 | SPEC-006 | Minor | `pending -> revoked` consent transition is semantically odd (decline vs withdrawal) with no disambiguation |
| 006-02 | SPEC-006 | Major | FormTemplate `schema` JSONB has no defined structure — agent can't build Pydantic validation |
| 006-03 | SPEC-006 | Major | `expire_consents` Celery task has no error handling defined (batch vs individual transactions) |
| 006-04 | SPEC-006 | Minor | Presigned URL expiry deferred to pending ADR-009 — no concrete default value |
| 007-01 | SPEC-007 | Minor | Stale "conductor" terminology in `bridge_rule_violation` error description |
| 007-02 | SPEC-007 | Minor | Directory layout and `cachetools.TTLCache` are implementation details, not behavioral contracts |
| 007-03 | SPEC-007 | Major | `GET /entity-types/{slug}/attributes` missing from master endpoint inventory |
| 007-04 | SPEC-007 | Major | CPT/ICD code write endpoints missing from master endpoint inventory |
| 007-05 | SPEC-007 | Major | Sub-specs define table schemas and API routes but not explicit request body schemas — most are inferable from tables, but ambiguous cases exist (server-derived fields, request-only fields) |
| 007-06 | SPEC-007 | Minor | `settings.write` overloaded for AppointmentType management with no design note |
| XSPEC-01 | Cross-spec | Minor | No spec explicitly states that notes are optional for invoicing — inferable but not declared |
| XSPEC-02 | Cross-spec | Major | EAV audit log has no guidance on PHI filtering for AttributeValue content |
| XSPEC-03 | Cross-spec | **Critical** | Row-level filtering conditions defined in SPEC-002 but SPEC-003, 004, 005 never reference how to apply them |
| XSPEC-04 | Cross-spec | Major | ~6 ambiguous endpoints need explicit request body schemas; ~6 straightforward ones can be inferred from table defs with a derivation rule |

**Totals:** 5 Critical, 24 Major, 13 Minor
