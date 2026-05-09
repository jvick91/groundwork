# ADR-002 — No `relationship()` — FK-only with explicit query-layer joins

**Date:** 2026-04-16
**Author:** claude-code
**Status:** Accepted (retrospective — implemented in `sql_models` branch). Amended 2026-05-09 to align with ADR-009.

## Context

SQLAlchemy's `relationship()` construct offers convenient navigation between models — `session.client.first_name` instead of an explicit join. It's a productivity win in many codebases. But it introduces hidden query behavior: lazy loading, N+1 pitfalls when iterating over a collection and dereferencing a related attribute, and a particular minefield with async SQLAlchemy around the `AsyncAttrs` / `expire_on_commit` / `greenlet_spawn` surface area.

In a multi-tenant PHI context, implicit queries are not merely inefficient — they are a safety hazard. A forgotten tenant filter inside a lazy-load cascade could return another organization's data. The enforcement surface is much easier to audit if every query is written explicitly where a human can see it.

## Decision

Models expose foreign-key columns only — e.g., `Session.client_instance_id: UUID` and `Session.provider_instance_id: UUID`. No `relationship()`, no `backref`, no implicit-load attributes of any kind.

All joins are written explicitly in the service or repository layer using `select(A).join(B, A.fk_id == B.id)`. When a route handler needs related data, the service constructs the exact query it needs. The ORM never issues a query implicitly on attribute access.

This is enforced by convention — there is nothing SQLAlchemy-level preventing `relationship()` from being added to a model. A lint check (grep / pre-commit) flags any `= relationship(` appearing in `models.py`. This lint is deferred until the first enforcement PR ships, but the policy is in effect now.

## Alternatives considered

**Full `relationship()` with default lazy loading.** Hidden queries, N+1 risk, async traps, and the tenant-filter safety issue above. Rejected outright.

**`relationship()` with eager-load strategies (`selectin`, `joined`).** Eager loading addresses the N+1 problem but still invites "just add `.relationship.foo`" habits that drift back toward implicit loading over time. Also over-fetches in read paths that don't need the related data. Rejected.

**`relationship()` only for rare navigation, FK-only for everything else.** Mixed pattern invites inconsistency. Teams lose track of when implicit loading is safe. Rejected in favor of a single, unambiguous rule.

## Consequences

- (+) All queries are explicit and visible at the service layer. N+1 cannot hide in a dereference chain.
- (+) Tenant filters are enforced at every query construction site — one site per aggregate, the `<Aggregate>Repository` class (see ADR-009) — not trusted to survive implicit cascades.
- (+) Async safety is straightforward — no greenlet or lazy-load hazards when awaiting a model attribute.
- (+) The boundary stays well-defined: models hold schema and invariants (validators, constraints, partial unique indexes, mutators, factories — see ADR-009); services orchestrate use cases; repositories own queries.
- (−) Boilerplate: every aggregate's queries are centralized in its `<Aggregate>Repository` class, where the explicit joins live (see ADR-009). No generic `BaseRepository` exists; the per-aggregate class is the operationalization of the explicit-join policy.
- (−) The ergonomic `parent.child.name` access pattern is gone. Teams coming from Django or Rails will find the discipline foreign and need a ramp-up.
- (−) Developer temptation: someone will want to add a `relationship()` "just for this one case." The lint check is the guard; without it, policy drift is near-certain.

## References

- Code anchor: `backend/app/models/` (every FK column is a scalar `UUID`, no `relationship()` anywhere)
- Related ADRs: ADR-001 (data model shape); ADR-009 (Service + Repository + Model-as-Entity — operationalizes the explicit-join policy via per-aggregate `<Aggregate>Repository` classes; no generic `BaseRepository` is introduced).
