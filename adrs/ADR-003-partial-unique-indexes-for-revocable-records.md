# ADR-003 — Partial unique indexes for revocable / void-able records

**Date:** 2026-04-16
**Author:** claude-code
**Status:** Accepted (retrospective — implemented in `sql_models` branch)

## Context

Several relational and domain records are "revocable" or "void-able" — they exist, but after some point are no longer active. The business invariant in each case is *"only one active row per logical key"*, but revoked or voided rows must be retained indefinitely for audit, so hard-deleting them to free a traditional unique constraint is not an option:

- `PersonRole.revoked_at: DateTime | None` — one active role assignment per `(organization, person, role, entity_instance)`.
- `RolePermission.revoked_at: DateTime | None` — one active permission grant per `(organization, role, permission)`.
- `Invoice.status` — one non-voided invoice per `session_id`. Voided invoices are preserved for audit.

A plain `UniqueConstraint` would prevent re-assigning a role after revoking its previous assignment (conflict with the revoked row). Enforcing the "one active" invariant purely in the application layer opens a check-and-insert race window that can yield duplicate active rows under concurrent writes.

## Decision

Partial unique indexes that exclude the inactive rows via a `WHERE` predicate, implemented with SQLAlchemy's `Index(..., unique=True, postgresql_where=...)` since `UniqueConstraint` does not support predicates:

- `PersonRole`: `UNIQUE (organization_id, person_id, role_id, entity_instance_id) WHERE revoked_at IS NULL`
- `RolePermission`: `UNIQUE (organization_id, role_id, permission_id) WHERE revoked_at IS NULL`
- `Invoice`: `UNIQUE (session_id) WHERE status != 'void'`

The uniqueness invariant is guaranteed at the database level regardless of application-layer bugs or concurrent-write races.

## Alternatives considered

**Plain `UniqueConstraint` + application-layer enforcement of "only one active".** Requires a check-then-insert pattern that has a race window under concurrent writes. Database-level guarantees are strictly safer, and the cost of a partial index is small.

**Separate "active" and "archive" tables.** Doubles table count for these three cases. Complicates any query that needs a cross-status view (e.g., "show me this person's full role history"). Increases migration and audit-trail complexity. Rejected.

**Soft-delete revoked rows via `deleted_at` and rely on `WHERE deleted_at IS NULL`.** Conflates revocation (a domain state transition — the role was taken away) with deletion (a retention/visibility concept — the record is no longer active). These are semantically distinct: a revoked role is still visible in "roles this person used to have"; a soft-deleted role is not. Collapsing them loses information.

## Consequences

- (+) Database-level guarantee of the "only one active" invariant, independent of application-layer correctness.
- (+) Revoked and voided rows are retained for audit with zero extra infrastructure.
- (+) The pattern is consistent across the three use cases — a reviewer who understands one understands all three.
- (+) Partial indexes are smaller than full indexes (inactive rows are excluded from the B-tree), so index size and maintenance cost are actually lower.
- (−) Queries that want "active rows only" must include the predicate (`WHERE revoked_at IS NULL` or `status != 'void'`). This is consistent with the soft-delete read-path pattern (`WHERE deleted_at IS NULL`), so it adds no new mental model — but it is a thing to remember.
- (−) Partial indexes with predicates are a PostgreSQL feature. If the project ever needs to support another database, these indexes would need re-engineering. Not a realistic concern given the HIPAA + audit posture; PostgreSQL is assumed.
- (−) Alembic autogenerate handles `postgresql_where` correctly in modern versions but has rough edges in older ones; migrations must be reviewed rather than blindly accepted.

## References

- Code anchor: `backend/app/models/models.py:311-316` (`PersonRole` partial index), `:350-355` (`RolePermission` partial index), `:607-612` (`Invoice` partial index)
- Related ADRs: ADR-003 (`SoftDeleteMixin` — a distinct mechanism from revocation, explicitly kept separate here)
