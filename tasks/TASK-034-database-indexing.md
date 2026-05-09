# TASK-034: Database Indexing Migration

**Status:** Not started
**Spec sections:** SPEC-007 §11 (all subsections)
**ADRs:** ADR-003, ADR-004 (EAV query performance), ADR-009
**Depends on:** TASK-011C, TASK-013, TASK-020, TASK-021, TASK-023, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029, TASK-030, TASK-031, TASK-032

## Objective

Create an Alembic migration that adds all indexes defined in SPEC-007 §11. This includes universal indexes (organization_id, deleted_at partial, created_at composite) and domain-specific indexes for auth flow, EAV queries, session overlap detection, billing, and audit log access.

## Acceptance Criteria

- [ ] Universal indexes on every table with organization_id per SPEC-007 §11.1
- [ ] Partial index `WHERE deleted_at IS NULL` on every table with deleted_at per SPEC-007 §11.1
- [ ] Composite index `(organization_id, created_at DESC)` on every table with created_at per SPEC-007 §11.1
- [ ] Domain-specific indexes per SPEC-007 §11.2:
  - [ ] Person: (auth_subject), (email)
  - [ ] PersonRole: (person_id, organization_id) WHERE revoked_at IS NULL; (organization_id, role_id) WHERE revoked_at IS NULL
  - [ ] RolePermission: (role_id) WHERE revoked_at IS NULL
  - [ ] Role: (organization_id, slug)
  - [ ] Permission: (slug)
  - [ ] EntityInstance: (organization_id, entity_type_id) WHERE deleted_at IS NULL
  - [ ] AttributeValue: (entity_instance_id)
  - [ ] Session: (organization_id, provider_instance_id, start_time, end_time) WHERE deleted_at IS NULL; (organization_id, client_instance_id) WHERE deleted_at IS NULL; (organization_id, status) WHERE deleted_at IS NULL
  - [ ] ClinicalNote: (session_id); (organization_id, author_instance_id) WHERE deleted_at IS NULL
  - [ ] Invoice: (session_id) WHERE status != 'void'; (organization_id, status) WHERE deleted_at IS NULL; (organization_id, client_instance_id) WHERE deleted_at IS NULL
  - [ ] InvoiceLineItem: (invoice_id) WHERE deleted_at IS NULL
  - [ ] Payment: (invoice_id) WHERE status = 'posted'
  - [ ] ClientInsurance: (organization_id, client_instance_id) WHERE is_active = true
  - [ ] ClientConsent: (organization_id, client_instance_id, consent_type_id) WHERE status = 'signed'
  - [ ] AuditLog: (organization_id, occurred_at DESC); (organization_id, resource_type, resource_id)
  - [ ] Document: (organization_id, document_type_id) WHERE deleted_at IS NULL
- [ ] Partial unique indexes on revocable-record tables (PersonRole, RolePermission, ClientInsurance, ClientConsent, Invoice) follow ADR-003's `WHERE deleted_at IS NULL` shape.
- [ ] Migration applies cleanly to a fresh database
- [ ] Migration applies cleanly as an upgrade from current schema
- [ ] Downgrade removes all added indexes

## Files

- `backend/alembic/versions/` (indexing migration)

## Non-goals

- Schema changes — this is indexes only
- Materialized views for EAV (deferred per ADR-004 upgrade path)
