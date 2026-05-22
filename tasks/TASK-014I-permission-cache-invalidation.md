# TASK-014I: Permission Cache Invalidation Strategy

**Status:** Not started
**Spec sections:** SPEC-002 §5 (resolution model), SPEC-007 §3.3 (caching contract)
**ADRs:** ADR-012 (the strategy this task documents and finalizes)
**Depends on:** TASK-014 (provides the `Person.permissions_version` column), TASK-015 (provides the cache implementation surface)

## Objective

Land the permission cache invalidation strategy from ADR-012 across all the code that mutates effective permissions. The `Person.permissions_version` column itself is migrated by TASK-014; the cache implementation lives in TASK-015. This task ensures the cache key shape `(person_id, organization_id, permissions_version)` is enforced, the per-request version read is implemented, and the write discipline in TASK-016 / TASK-017 / TASK-014J is verified by tests.

Most of this task is **documentation, tests, and review** — the increment logic ships inside the tasks that mutate permissions. This task's role is to make sure the strategy is coherent end-to-end and to be the named place where the cache-correctness invariants are checked.

## Acceptance Criteria

- [ ] `backend/app/services/auth_service.py` (from TASK-015): permission cache key is `(person_id, organization_id, permissions_version)`. Confirmed by code review and a test that fails if any component is removed.
- [ ] Resolver loads the current `Person.permissions_version` via an indexed PK lookup on every cache-resolution call; result is included in the cache key.
- [ ] 60-second TTL still applies as a memory ceiling; **not** as a staleness window. Documented in the code with the rationale from ADR-012.
- [ ] Integration tests verify the zero-staleness property:
  - [ ] `test_role_revocation_invalidates_cache_immediately` — assign a role, hit a permission-gated endpoint (200), revoke the role, hit again immediately (403). No sleep, no TTL wait.
  - [ ] `test_role_permission_grant_invalidates_cache_for_all_holders` — Person A and Person B both hold role R; granting a new permission to R produces immediate effect for both.
  - [ ] `test_hierarchy_change_invalidates_cache` — Role R inherits from parent P; changing P's grants reflects on R's holders immediately.
  - [ ] `test_force_kill_invalidates_cache` — TASK-014J's force-kill flow increments `permissions_version`; verifies cached entries are unreachable.
- [ ] Granularity-tradeoff documented in code comments: `permissions_version` is per-Person, not per-(Person, org); cross-org cache invalidation on single-org change is acknowledged and the escape hatch (move to per-(person, org) table) is noted.
- [ ] LISTEN/NOTIFY rejection rationale referenced in the task; no LISTEN/NOTIFY code path exists.
- [ ] Logout flow note: routine logout is fully handled by Auth0 + SPA SDK per TASK-014B. The force-kill path is TASK-014J. This task does **not** ship a backend logout endpoint.

## Files

- (No new files for this task itself; references TASK-014, TASK-015, TASK-016, TASK-017, TASK-014J implementations)
- `backend/tests/test_auth/test_cache_invalidation.py` (new — integration tests above)

## Non-goals

- The cache implementation primitives (TASK-015 owns those)
- The `Person.permissions_version` migration (TASK-014 owns it)
- The increment write logic in role/permission/personrole mutations (TASK-016, TASK-017 own those)
- Force-kill endpoint (TASK-014J)
- Routine logout (Auth0 + SPA SDK; no backend code)
