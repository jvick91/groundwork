# TASK-002: Base ORM Patterns, Enums, & Alembic Configuration

**Status:** Complete
**Spec sections:** SPEC-007 §4.3, §4.4, §4.6; SPEC-000 §3
**ADRs:** ADR-001, ADR-002 (FK-only, no relationship), ADR-003 (partial unique indexes)
**Depends on:** TASK-001

## Objective

Define the base SQLAlchemy model class with shared patterns: UUID primary keys (v4, server-generated), timestamp columns (`created_at`, `updated_at`), soft-delete mixin (`deleted_at`), and the `StrEnum + native_enum=False` convention for all status/type enums. Establish the FK-only policy (no `relationship()`) per ADR-002. Configure Alembic to detect partial unique indexes per ADR-003.

## Acceptance Criteria

- [x] Base model class provides UUID PK, `created_at`, `updated_at` columns with UTC defaults
- [x] Soft-delete mixin provides nullable `deleted_at` column
- [x] All enums use `StrEnum` with uppercase member names and `native_enum=False` per SPEC-007 §4.6
- [x] Enums defined: `SessionStatus`, `NoteStatus`, `NoteFormat`, `InvoiceStatus`, `PaymentStatus`, `PaymentMethod`, `PayerType`, `ConsentStatus`, `FormType`, `InsurancePriority`, `FieldType`, `RoleDomain` (renamed from `PrimaryDomain` during implementation)
- [x] `Permission.action` is stored as a plain `String` column, NOT an enum. Rationale: SPEC-002 §3 seeds actions (`create`, `void`, `record`, `revoke`, `send`, `configure`, `manage`) that fall outside the narrower list in SPEC-002 §2's field description. The authoritative set is the seed matrix, which extends freely as new domain permissions are added. A stored enum would force a spec revision and a migration on every new permission
- [x] No `relationship()` appears anywhere in models — FK columns are scalar UUIDs per ADR-002
- [x] Money columns use Integer type with `_cents` suffix per SPEC-007 §4.4
- [x] Alembic env.py supports `postgresql_where` for partial unique indexes per ADR-003
- [x] All models importable from a single `app.models` entry point

## Scope expansion (recorded 2026-04-23)

During implementation this task shipped the entire 26-table schema in a single initial migration (`a68701f39fed_initial_schema.py`) and defined every domain model in `backend/app/models/models.py` (845 lines). The following models — originally scoped to later tasks — are already present and their tables already created:

| Model(s) | models.py line | Nominal owner task |
|---|---|---|
| `Organization` | 139 | TASK-009 |
| `EntityType`, `EntityAttribute` | 152, 174 | TASK-010 |
| `EntityInstance`, `AttributeValue` | 193, 211 | TASK-011C |
| `Person` | 236 | TASK-012 |
| `Role`, `Permission`, `PersonRole`, `RolePermission` | 257, 282, 302, 342 | TASK-013 |
| `AppointmentType` | 382 | TASK-020 |
| `Session` | 404 | TASK-021 |
| `ClinicalNote` | 442 | TASK-023 |
| `CPTCode`, `ICDCode` | 490, 507 | TASK-025 |
| `InsurancePayer`, `ClientInsurance` | 523, 538 | TASK-026 |
| `Invoice`, `InvoiceLineItem`, `Payment` | 576, 620, 644 | TASK-027/028 |
| `AuditLog` | 686 | TASK-006 |
| `DocumentType`, `Document` | 716, 737 | TASK-029/030 |
| `ConsentType`, `ClientConsent` | 765, 784 | TASK-029/031 |
| `FormTemplate` | 821 | TASK-032 |

Each affected downstream task has been re-scoped — the model + migration sub-items are marked done, and the remaining work is schemas, services, routers, lifecycle rules, seed data, and tests. See each task's "Pre-existing artifacts" section.

## Files

- `backend/app/models/models.py` (or split per SPEC-007 §12.1)
- `backend/app/models/__init__.py`
- `backend/alembic/env.py`

## Non-goals

- Individual domain model definitions (TASK-006+)
- Seed data (domain-specific tasks)
