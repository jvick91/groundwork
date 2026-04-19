# ADR-001 — Hybrid EAV + concrete data model

**Date:** 2026-04-16
**Author:** claude-code
**Status:** Accepted (retrospective — implemented in `sql_models` branch)

## Context

Mental-health practices differ in what they track per client: intake fields, custom assessments, practice-specific metadata. A purely normalized schema forces a uniform shape that will not accommodate this variance without constant schema migrations. A purely EAV approach, on the other hand, loses foreign-key integrity on the data where integrity is load-bearing — sessions, invoices, clinical notes, insurance claims. Both extremes fail the project's constraints.

The constraints are:
- Flexibility for per-practice custom attributes (real, observed variance in intake and clinical data).
- Referential integrity for domain-critical records (HIPAA-audit traceability, billing correctness, scheduling consistency).
- Queryable by both fixed and variable dimensions (list clients by age is EAV; list sessions by provider is concrete).
- Common-case performance on concrete data (not every query should pay an EAV cost).

## Decision

Hybrid schema, 26 tables total:

- **EAV core (6 tables)** — `Organization`, `Person`, `EntityType`, `EntityAttribute`, `EntityInstance`, `AttributeValue`. These carry practice-defined custom entities and their variable attribute values.
- **Concrete layer (20 tables)** — `Session`, `Invoice`, `InvoiceLineItem`, `Payment`, `ClinicalNote`, `AppointmentType`, `CPTCode`, `ICDCode`, `InsurancePayer`, `ClientInsurance`, `AuditLog`, `DocumentType`, `Document`, `ConsentType`, `ClientConsent`, `FormTemplate`, `Role`, `Permission`, `PersonRole`, `RolePermission`. These carry domain-critical data with first-class foreign-key relationships.

Custom EntityTypes and their instances live in the EAV core. Domain objects reference concrete tables directly. Bridge points (e.g., `Session.client_instance_id → EntityInstance.id`) tie the two layers.

## Alternatives considered

**Pure normalized schema.** Every per-practice custom field becomes its own column — and therefore its own migration per practice. Operationally infeasible at multi-tenant scale: cannot ship a schema change to production every time a practice adds an intake question.

**Pure EAV for everything.** Sessions, invoices, notes all lose foreign-key integrity. Every domain query becomes an EAV join. Audit trails become much harder to reconstruct. HIPAA traceability suffers.

**Document store (MongoDB or JSONB-only).** Loses the relational querying we rely on for billing and clinical reporting. HIPAA audit requirements are harder to satisfy without the row-level trail a relational DB gives us. Team SQL expertise does not translate.

## Consequences

- (+) Practices gain flexibility without schema migrations.
- (+) Domain core retains foreign-key integrity where it matters.
- (+) Common-case queries (list sessions, list invoices) remain simple and cheap.
- (+) Clear separation: reviewers can reason about the concrete layer using standard relational intuition; EAV complexity is bounded to 6 tables.
- (−) Two mental models coexist (relational concrete, EAV custom). Onboarding has a higher cost than a pure-relational schema.
- (−) List queries over the EAV layer (list clients filtered by custom attribute) require N joins. Naive implementation ships for MVP; if real-world scale exceeds what naive joins handle, the optimization path is a documented future work item, not an unknown risk.
- (−) Bridge rules (a `provider_instance_id` must reference an EntityInstance whose EntityType is a provider role) must be validated at the service layer, not the DB.

## References

- Specs: SPEC-001 (entire); SPEC-000 §data-model-overview
- Code anchor: `backend/app/models/models.py:139-229` (EAV core), `:236-845` (concrete)
- Related ADRs: ADR-002 (UUID identifiers used across both layers), ADR-003 (mixin composition), ADR-005 (no `relationship()`)
