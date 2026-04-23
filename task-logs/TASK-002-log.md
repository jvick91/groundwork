# TASK-002 Log — Base ORM Patterns, Enums, & Alembic Configuration

**Agent:** (backfilled retroactively)
**Branch:** (pre-dates `tasks/breakdown`)
**Date completed:** (pre-2026-04-22; marked Complete in STATE.md before task logs were introduced)
**Log written:** 2026-04-23

## What Was Done

Established the base ORM conventions:

- **Base class & mixins** in `backend/app/models/models.py`: `Base` (DeclarativeBase), `IdMixin` (UUID v4 server-generated PK), `TimestampMixin` (`created_at`, `updated_at` with UTC defaults), `SoftDeleteMixin` (nullable `deleted_at`).
- **Enums** — all `StrEnum` with `native_enum=False`, stored as VARCHAR:
  `FieldType` (L45), `RoleDomain` (L56 — renamed from `PrimaryDomain`), `SessionStatus` (L63), `NoteFormat` (L73), `NoteStatus` (L79), `InsurancePriority` (L87), `PaymentMethod` (L92), `PayerType` (L101), `PaymentStatus` (L107), `InvoiceStatus` (L112), `ConsentStatus` (L121), `FormType` (L128).
- **FK-only policy** per ADR-002 — no `relationship()` anywhere in models; all joins written explicitly in the query layer.
- **Money in cents** per SPEC-007 §4.4 — every monetary column is `Integer` with a `_cents` suffix.
- **Alembic env.py** supports `postgresql_where` for partial unique indexes per ADR-003.
- All models importable from `app.models`.

## Scope expansion (the big finding from 2026-04-23 audit)

This task went far beyond its written scope. Rather than landing base patterns and stopping, the implementer defined the entire 26-table schema in `backend/app/models/models.py` (845 lines) and emitted a single initial Alembic migration (`backend/alembic/versions/a68701f39fed_initial_schema.py`, 510 lines) that creates all 26 tables in one shot.

**Models pre-landed (nominal owner → models.py line):**

| Nominal owner | Model(s) | Line |
|---|---|---|
| TASK-009 | `Organization` | 139 |
| TASK-010 | `EntityType`, `EntityAttribute` | 152, 174 |
| TASK-011C | `EntityInstance`, `AttributeValue` | 193, 211 |
| TASK-012 | `Person` | 236 |
| TASK-013 | `Role`, `Permission`, `PersonRole`, `RolePermission` | 257, 282, 302, 342 |
| TASK-020 | `AppointmentType` | 382 |
| TASK-021 | `Session` | 404 |
| TASK-023 | `ClinicalNote` | 442 |
| TASK-025 | `CPTCode`, `ICDCode` | 490, 507 |
| TASK-026 | `InsurancePayer`, `ClientInsurance` | 523, 538 |
| TASK-027/028 | `Invoice`, `InvoiceLineItem`, `Payment` | 576, 620, 644 |
| TASK-006 | `AuditLog` | 686 |
| TASK-029/030 | `DocumentType`, `Document` | 716, 737 |
| TASK-029/031 | `ConsentType`, `ClientConsent` | 765, 784 |
| TASK-032 | `FormTemplate` | 821 |

**Tables created by initial migration** (25 `op.create_table` calls + the `alembic_version` table): organizations, people, audit_logs, consent_types, cpt_codes, document_types, entity_types, form_templates, icd_codes, insurance_payers, permissions, roles, appointment_types, documents, entity_attributes, entity_instances, role_permissions, attribute_values, client_consents, client_insurances, person_roles, sessions, clinical_notes, invoices, invoice_line_items, payments.

## Decisions Made

- **Renamed `PrimaryDomain` → `RoleDomain`** during implementation. The original spec called for `PrimaryDomain`; in code it reads more naturally as `RoleDomain`. Downstream RBAC work (TASK-013, TASK-015) must use `RoleDomain`.
- Monolithic `models.py` rather than splitting per SPEC-007 §12.1. Keeping all models in one file was a simplicity-over-ceremony judgment; the `app.models` entry point remains single-import either way.
- Initial schema committed as one migration (`a68701f39fed_initial_schema.py`) rather than per-domain migrations. Domain tasks that want extra indexes, partial indexes (ADR-003), or seed data will issue follow-up migrations.

## Deviations from Task

- **What changed:** shipped all 26 domain models + their tables, not just the base patterns.
- **Why:** one-pass convenience during implementation.
- **Impact:** Significant. Every downstream domain task (006, 009, 010, 011C, 012, 013, 020, 021, 023, 025–032) had its "create model X" and "Alembic migration creates table Y" ACs silently satisfied. Without this log, later agents would either re-create models (duplicates, migration conflicts) or look for them in the wrong place. All affected task files have been updated with a **Pre-existing artifacts** section pointing at the specific `models.py:<line>` and calling out what work actually remains (schemas, services, routers, lifecycle rules, seed data, partial unique indexes where not yet in the migration, tests).
- **Other renamings:** `PrimaryDomain` → `RoleDomain` (see Decisions).

## Open Items

- Some partial unique indexes required by ADR-003 (e.g. `PersonRole.UNIQUE(..., ...) WHERE revoked_at IS NULL`, one-active-invoice-per-session, one-active-priority per client/payer, one-signed-consent-per-type) may not be fully in the initial migration. Each consuming task (013, 026, 027, 031) should verify and issue a follow-up Alembic migration if absent.
- `AuditLog` has no DB-level UPDATE/DELETE block yet — TASK-006 owns that migration.
- Seed data for EntityType (TASK-010), RBAC roles/permissions (TASK-013), DocumentType/ConsentType per-org (TASK-029), and FormTemplate per-org (TASK-032) still needs to be authored and emitted as seed migrations.
