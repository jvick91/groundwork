# ADR-012 — Permission cache invalidation via Person.permissions_version

**Date:** 2026-05-21
**Author:** claude-code
**Status:** Proposed

## Context

TASK-015 designs an in-process TTL cache for the effective permission set per `(person_id, organization_id)`, with a 60-second TTL per SPEC-007 §3.3. The cache solves the read amplification of role-hierarchy walks: every authenticated request would otherwise re-walk the parent_role_id chain and re-union RolePermission grants. With caching, the walk happens at most once per minute per (person, org).

The TTL alone has a HIPAA-relevant gap: when a `PersonRole` is revoked — clinician terminated, role downgraded, grant rescinded — the cached effective permissions for that person continue to grant access for up to 60 seconds. In a multi-worker uvicorn or gunicorn deployment, "same process" invalidation (which TASK-015's draft mentions) does not propagate to other workers, so the effective staleness window is the full TTL across the fleet.

For routine permission changes that is acceptable. For revocation tied to a security event — fired clinician, suspected credential compromise — even 60 seconds of continued access is a documented audit finding. The cache invalidation strategy must reduce that window to zero for any state-changing operation that the system itself knows about.

Three approaches were considered:

1. **Short TTL only**, accepting the staleness window. Simplest. Worst staleness.
2. **Postgres `LISTEN`/`NOTIFY`** to broadcast invalidation events across workers.
3. **Per-Person generation column** (`permissions_version`) that the resolver reads on every cache lookup, comparing against the cached value.

LISTEN/NOTIFY is technically attractive — explicit invalidation, low latency, no application-side coordination beyond subscribing. In practice, it has two failure modes that are uncomfortable for a HIPAA-bound platform:

- It requires persistent sessions to be useful. With PgBouncer in transaction-pooling mode (the default for FastAPI deployments and the configuration this codebase plans to use), session-level state including `LISTEN` subscriptions does not survive between transactions. Moving the listener connection to session mode means special-casing one connection out of the pool, which is operationally fragile.
- Notifications can be missed during reconnection. If a worker's listener connection drops and reconnects, any `NOTIFY` fired during the gap is lost. There is no replay. The application would need a fallback (e.g., periodic full cache flush) to bound the gap — at which point the explicit-invalidation property is no longer reliable.

The generation-column approach trades one extra indexed PK read per request for zero-staleness correctness, with no inter-process coordination. The read cost is sub-millisecond and well-bounded; the operational profile is plain SQL, no special pooling, no listener lifecycle to manage.

## Decision

### `Person.permissions_version` column

Add an integer column to `Person`:

```sql
ALTER TABLE person ADD COLUMN permissions_version INTEGER NOT NULL DEFAULT 0;
```

The migration is bundled with TASK-014 (the JWT middleware task) as part of the foundational auth chain.

### Cache key shape

The TASK-015 in-process cache keys on `(person_id, organization_id, permissions_version)`. The cached value is the effective permission set for that triple. On read:

1. Resolver loads the current `Person.permissions_version` via a single indexed PK lookup.
2. Build the cache key with the current version.
3. If a value exists for that key and is within the 60-second TTL, return it (cache hit).
4. Otherwise, perform the four-step resolution from SPEC-002 §5, store under the new key, return the result (cache miss + reload).

Cache entries keyed on stale versions become unreachable as soon as the version is incremented. They expire from memory naturally via the 60-second TTL ceiling.

### Write discipline

Every database mutation that could change a Person's effective permission set must increment `permissions_version` for the affected Person in the same transaction as the mutation:

- `PersonRole` insert (assignment): increment for the assigned Person.
- `PersonRole` update setting `revoked_at` (revocation): increment for the affected Person.
- `RolePermission` insert/update (grant or revoke at role level): increment `permissions_version` for *every Person currently holding that role*. This is a wider write but it is the correct semantic — the role's effective grants changed for every holder.
- `Role` update that changes `parent_role_id` (hierarchy edit): increment for every Person holding any role whose hierarchy walk includes the modified role.
- TASK-014J force-kill: increment for the targeted Person as part of the force-revoke transaction.

This write discipline lives in the service-method layer for TASK-016 (role and permission management), TASK-017 (PersonRole assignment), and TASK-014J. Each task's acceptance criteria reference this ADR.

### Staleness window: zero (for tracked changes)

For any database state change that the application knows about, the cache is correct on the very next request after the mutating transaction commits. The version check on read happens before the cache lookup, so a stale cached entry is structurally unreachable.

The 60-second TTL remains as a memory ceiling: cache entries keyed on old versions are eventually evicted, bounding the in-process cache size to roughly `live_persons * max_orgs_per_person` entries. The TTL is not the staleness window.

### Granularity: per-Person, not per-(Person, organization)

`permissions_version` is a single integer per `Person`, not a row per `(person_id, organization_id)` pair. Consequence: revoking a `PersonRole` in org_1 invalidates the cache for that Person's org_2 access too — even though org_2's grants did not change.

Cost: one extra cache reload on the next org_2 request after an org_1 mutation. For a Person who mostly works in one organization at a time, this is invisible. For a Person who holds active roles in many organizations simultaneously and switches between them rapidly, every grant change in any org evicts the cache for all of them.

This tradeoff is accepted for MVP. If profiling later shows it matters, the escape hatch is to move `permissions_version` into a separate `(person_id, organization_id)` table — same algorithm, finer grain, no call-site changes outside the resolver and the increment logic.

### Per-request cost

Every authenticated request that does a permission check pays one extra indexed PK read on `Person.permissions_version`. With a PK index in shared buffers, this is sub-millisecond and well within the request budget. The alternative (LISTEN/NOTIFY) is zero-cost on hit but unbounded-cost on the reconnect-and-replay path; the constant-cost-per-request approach is preferred for predictability.

## Consequences

**For:**

- HIPAA-relevant permission revocations propagate within one request. The 60-second TTL is no longer a security-relevant staleness window.
- The strategy is multi-worker safe by construction. No inter-process coordination is needed — every worker reads the authoritative version from the database.
- PgBouncer-compatible in transaction-pooling mode. No special connection lifecycle.
- The cache key shape is explicit and self-documenting: `(person_id, organization_id, permissions_version)`. Any code review that sees a cache key with fewer components knows to look harder.

**Against:**

- One extra indexed PK read per authenticated request. Sub-millisecond but non-zero. For most workloads invisible; for an extreme high-RPS endpoint with deep permission gating it would be measurable.
- The per-Person granularity invalidates cross-org cache entries. Acceptable for MVP; an escape hatch exists.
- The write discipline is dispersed across multiple service methods (TASK-015, 016, 017, 014J). Forgetting to increment in a new code path produces silent cache staleness on hot paths — exactly the failure mode the cache version is supposed to prevent. Each task's acceptance criteria must explicitly require the increment.
- The `permissions_version` increment for `RolePermission` and `Role` hierarchy changes can touch many Person rows. For seed catalog edits this is unobjectionable; for routine role-permission grants it is a small additional write per Person holding the role.

## Alternatives considered

**Short TTL only (60 seconds, no version check).** Simplest. Rejected: permission revocation has a 60-second worst-case window across the fleet, which is a HIPAA audit concern.

**Postgres `LISTEN`/`NOTIFY` for cross-worker invalidation.** Discussed in Context. Rejected: PgBouncer transaction-pooling incompatibility, lost-notification edge cases under reconnect, requires fallback cache flush which undermines the explicit-invalidation property.

**Redis pub/sub for cross-worker invalidation.** Adds a Redis dependency to the stack. Rejected: Redis is not currently on the stack, and adding infrastructure to solve a problem the database can solve adequately is over-engineering.

**Per-(Person, organization) generation table.** Finer-grained invalidation; cross-org changes don't invalidate other orgs. Rejected for MVP because the cost of the per-Person granularity is acceptable and the migration to per-(Person, organization) is straightforward if needed later.

**Immediate cache eviction on every write via in-process event bus.** Each worker subscribes to a process-local event bus that mutators publish to. Rejected: solves the same-process case but not the multi-worker case, which is the actual failure mode.

## Phased plan

- [ ] Epic 1: TASK-014 adds the `permissions_version` column migration alongside its middleware work.
- [ ] Epic 2: TASK-015's cache implementation keys on the four-component tuple including `permissions_version`; resolver reads the current version on every cache lookup.
- [ ] Epic 3: TASK-016 acceptance criteria require `permissions_version` increment on every `RolePermission` grant/revoke and every `Role` hierarchy update affecting holders.
- [ ] Epic 4: TASK-017 acceptance criteria require `permissions_version` increment on every `PersonRole` assignment and revocation.
- [ ] Epic 5: TASK-014J (force-kill) increments `permissions_version` as part of its revoke transaction (step 3 of the documented flow).
- [ ] Epic 6: TASK-014I documents this strategy in the task file and ships any cache-implementation code that doesn't already exist after TASK-015.

## References

- ADR-009 — service + model-as-entity layering. The increment lives in service-method code per ADR-009's conventions.
- ADR-010 — consolidated auth architecture; this ADR is its permission-resolution layer.
- ADR-011 — invitation lifecycle; the accept transaction's `permissions_version` increment is part of this strategy.
- SPEC-002 §5 — four-step authorization resolution model.
- SPEC-002 §4 — revocation rule (active grants require `revoked_at IS NULL`).
- SPEC-007 §3.3 — permission resolution and caching contract.
