# TASK-002: Base ORM Patterns, Enums, & Alembic Configuration

**Status:** Complete
**Spec sections:** SPEC-007 §4.3, §4.4, §4.6; SPEC-000 §3
**ADRs:** ADR-002 (FK-only, no relationship), ADR-003 (partial unique indexes)
**Depends on:** TASK-001

## Objective

Define the base SQLAlchemy model class with shared patterns: UUID primary keys (v4, server-generated), timestamp columns (`created_at`, `updated_at`), soft-delete mixin (`deleted_at`), and the `StrEnum + native_enum=False` convention for all status/type enums. Establish the FK-only policy (no `relationship()`) per ADR-002. Configure Alembic to detect partial unique indexes per ADR-003.

## Acceptance Criteria

- [ ] Base model class provides UUID PK, `created_at`, `updated_at` columns with UTC defaults
- [ ] Soft-delete mixin provides nullable `deleted_at` column
- [ ] All enums use `StrEnum` with uppercase member names and `native_enum=False` per SPEC-007 §4.6
- [ ] Enums defined: `SessionStatus`, `NoteStatus`, `NoteFormat`, `InvoiceStatus`, `PaymentStatus`, `PaymentMethod`, `PayerType`, `ConsentStatus`, `FormType`, `InsurancePriority`, `FieldType`, `PrimaryDomain`, `PermissionAction`
- [ ] No `relationship()` appears anywhere in models — FK columns are scalar UUIDs per ADR-002
- [ ] Money columns use Integer type with `_cents` suffix per SPEC-007 §4.4
- [ ] Alembic env.py supports `postgresql_where` for partial unique indexes per ADR-003
- [ ] All models importable from a single `app.models` entry point

## Files

- `backend/app/models/models.py` (or split per SPEC-007 §12.1)
- `backend/app/models/__init__.py`
- `backend/alembic/env.py`

## Non-goals

- Individual domain model definitions (TASK-006+)
- Seed data (domain-specific tasks)
