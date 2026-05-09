# TASK-008A: Service & Router Layer Conventions (Shared Plumbing)

**Status:** Complete (rewritten 2026-05-09 to align with ADR-009)
**Spec sections:** SPEC-007 §12.2 (layer responsibilities), §12.3 (dependency injection)
**ADRs:** ADR-002 (FK-only, explicit queries), ADR-008 (request-context & auth/org boundary), ADR-009 (Service + Repository + Model-as-Entity)
**Depends on:** TASK-002, TASK-003, TASK-004, TASK-006, TASK-007, TASK-008

## Objective

Produce the shared plumbing every domain router/service/repository will consume — and nothing else. As of the 2026-05-09 architecture reset, the conventions established here mirror ADR-009: a four-layer architecture with class-per-aggregate Service and Repository, an injected `AuditWriter` collaborator, and a route-level exception handler that owns failure-audit writes.

The reference implementation is the Organization slice (TASK-009 + this task's amendments). TASK-010 (EntityType / EntityAttribute) is the second consumer and validates that the pattern scales beyond a single aggregate.

## Conventions

### Router pattern (ADR-009)

- One file per spec domain under `app/routers/` — `routers/<domain>.py`. Registered in `main.py`.
- A route depends on a single `<Aggregate>Service` factory (`Depends(get_<aggregate>_service)`). Routes do **not** depend on `db`, `auth`, or any SQLAlchemy import.
- `actor_id` and `tenant_id` are closed over in the Service constructor by `core/dependencies.py`. The route passes the request body and path parameters; the service does the work.
- Permission via `dependencies=[require_permission("permission.slug")]` on the route decorator.
- Routes return Pydantic response models. They never construct ORM objects, never call `db.add` / `db.commit`.

### Service pattern (ADR-009)

- One file per aggregate: `services/<aggregate>_service.py` containing one `<Aggregate>Service` class.
- Constructor injection: `__init__(self, repo, audit, lifecycle, tenant_id, actor_id, ...)`. Collaborators are wired by `core/dependencies.py`. No global state.
- Methods orchestrate use cases: load via repository → mutate via model methods (mutators / factories) → persist via repository → write success audit via `AuditWriter`.
- Services raise domain exceptions (subclasses of `GroundworkError`); they never raise `HTTPException` and never commit.
- Services do **not** import `select`, call `session.execute`, or hold a SQLAlchemy reference except via the repository.

### Repository pattern (ADR-009)

- One file per aggregate: `repositories/<aggregate>_repository.py` containing one `<Aggregate>Repository` class.
- Constructor takes `AsyncSession` (via `Depends(get_db)`). That is the only dependency.
- Owns every `select` / `insert` / `update` / `delete` and every explicit join (preserving ADR-002).
- Returns Model instances. Does not enforce business rules and does not write audit.
- Method names: `get`, `list_for_<scope>`, `find_by_<field>` for reads; `save` for writes; `delete` is rare (prefer soft-delete via a model mutator).
- No generic `BaseRepository` — the per-aggregate class IS the explicit-join policy operationalized.

### Model-as-entity pattern (ADR-009)

- The Model is the domain entity. There is no separate domain class.
- Invariants live on the Model: `@validates(...)` for field shape, `CheckConstraint(...)` for SQL invariants, partial unique indexes (ADR-003) for revocability rules, instance mutator methods for state transitions (`org.deactivate()`, `et.assert_mutable()`), `@classmethod` factories for non-trivial construction (`Organization.from_create(data)`).
- FK-only — no `relationship()` (ADR-002).

### Audit pattern (ADR-009)

- **Success path.** Each Service holds an `AuditWriter` injected via `Depends(get_audit_writer)`. The writer adds an `AuditLog` row to the request session and flushes; commit happens at the end of the request via `get_db`. PHI is filtered via `app.core.phi.filter_phi`.
- **Failure path.** The `GroundworkError` exception handler in `app/main.py` is the single owner of failure-audit writes. When an exception carries the audit-context fields (`audit_action`, `audit_entity_type`, `audit_entity_id`, `audit_actor_id`), the handler opens a *fresh* session, instantiates an `AuditWriter`, writes a row with `outcome="failure"`, commits, and closes — independent of the request transaction.
- Domain exceptions never write audit themselves. Services raise; the handler audits and translates.
- `outcome` is a non-null `String(16)` column on `AuditLog` constrained to `('success', 'failure')` — see migration `e730417d99c0_add_audit_log_outcome`.

### Tenant + actor context

- `tenant_id: UUID` and `actor_id: UUID | None` enter Services as primitive UUID parameters.
- Forward reference: ADR-008 introduces a structured `RequestContext` covering tenant + auth-provider + org boundary. TASK-014 (auth middleware) and TASK-015 (permission resolution) wire that decision in. Until then, primitive UUIDs are the contract.

### Org-scoped query pattern

- Every tenant-scoped repository method that lists or fetches multi-row data filters by `tenant_id`: `Model.organization_id == tenant_id`.
- Soft-delete domains add `Model.deleted_at.is_(None)` to read paths.
- Both filters are applied inside the repository — services never re-apply them.

### No module-level mutable state

Files under `services/`, `repositories/`, `models/`, `enums/`, and `schemas/` declare no top-level data: lookup dicts, allowlists, registries, type aliases, regex patterns used by `Field(pattern=...)`. Inline at use, or encapsulate as a class attribute on a private class with an `lru_cache`d factory in `core/dependencies.py`. Imports, function defs, and class defs are not "variables" for this rule. `app/main.py` and `alembic/env.py` are framework boilerplate and out of scope.

### Naming schema (ADR-009)

| Kind | Pattern | Example |
|---|---|---|
| Service class / file | `<Aggregate>Service` / `<aggregate>_service.py` | `OrganizationService` / `organization_service.py` |
| Repository class / file | `<Aggregate>Repository` / `<aggregate>_repository.py` | `EntityTypeRepository` |
| Model class | `<Aggregate>` (one of multiple per `models/<domain>.py`) | `EntityAttribute` |
| Schema class | `<Aggregate>Create` / `Update` / `Response` | `OrganizationResponse` |
| Enum class | `<Concept>` | `SessionStatus` |
| Domain exception | `<Concept>Error` or `<Aggregate><State>` | `OrganizationAlreadyInactive` |
| Collaborator | `<Concept>Writer` / `Dispatcher` / `Client` | `AuditWriter` |
| Depends factory | `get_<thing>` | `get_organization_service` |
| Model mutator | imperative verb | `org.deactivate()` |
| Model factory | `@classmethod` named after intent | `Organization.from_create(data)` |
| Repository read | `get` / `list_for_<scope>` / `find_by_<field>` | `repo.list_for_page(params)` |
| Repository write | `save` (delete is rare) | `repo.save(org)` |
| Service method | use-case verb phrase | `service.create(data)` |
| Lifecycle hook | `register_post_<event>` / `on_<event>` | `lifecycle.register_post_create(fn)` |

### Forbidden names

- **Files:** `common.py`, `utils.py`, `helpers.py`, `misc.py`, `lib.py`, `shared.py`, `manager.py`, `handler.py`, `processor.py`, `worker.py`, `_lifecycle.py`, `_hooks.py`, `_transaction.py`.
- **Classes:** `BaseService`, `BaseRepository`, `GenericRepository`, `<X>Manager`, `<X>Helper`, `<X>Util`.
- **Folders:** `helpers/`, `utils/`, `common/`, `lib/`, `misc/`, `managers/`, `handlers/`, `processors/`, `middleware/`.

## Acceptance Criteria

- [x] `app/core/dependencies.py` exports `get_db`, `get_audit_writer`, the per-aggregate factories (`get_<aggregate>_service`, `get_<aggregate>_repository`), and the auth re-exports (`get_auth_context`, `current_person`, `current_org`, `require_permission`).
- [x] Stubs are feature-flagged via `settings.auth_stub_enabled` so TASK-014/015 can flip the flag off in one place.
- [x] `app/services/audit_service.py` exports an `AuditWriter` class and the `_AuditScope` dataclass; the legacy `log_action` free function is gone.
- [x] `app/main.py` registers a `GroundworkError` handler that writes a failure audit in a fresh session when the exception carries audit-context fields.
- [x] Pagination helpers from TASK-004 are imported from `app.core.pagination` (relocated from `app.utils.pagination` per ADR-009 forbidden-folder rule).
- [x] `app/routers/__init__.py` documents the required router shape (`Depends(get_<aggregate>_service)`, no `db`, no auth args on the route signature).
- [x] `docs/conventions.md` rewritten to mirror ADR-009 (this task's "Conventions" section is the canonical source; the doc now points readers at ADR-009 for full architecture context).
- [x] Tests: `tests/test_services/test_audit_writer.py` — verifies `AuditWriter.write` adds a row, applies PHI filter, flushes (does not commit), populates `outcome`, and supports the `organization_id` override for tenant-creation paths.
- [x] Tests: stub-dependency shape tests — `tests/test_cross_cutting/test_stub_dependencies.py` asserts `current_person` returns a dict with `id`, `email`, `is_active`; `current_org` returns a dict with `id`, `name`, `timezone`; `require_permission("any.slug")` allow-lists while `auth_stub_enabled=true`; rejects when the flag is off.
- [x] No domain endpoints, models, schemas, or tables are introduced by this task.

## Open follow-ups

- **Failure-audit integration test.** A test for the end-to-end `404 → AuditLog(outcome='failure')` path requires a shared org-seed fixture in `tests/test_core/` (the existing `tests/test_eav/conftest.py` only seeds for the EAV suite). Tracked here; lift the fixture when the second cross-cutting test needs it.
- **Structured RequestContext.** ADR-008 introduces `RequestContext` (request-id, tenant, actor, auth provider). Wired by TASK-014.

## Files (post-architecture-reset)

- `backend/app/core/dependencies.py`
- `backend/app/core/config.py` (renamed from `settings.py`; `auth_stub_enabled` flag)
- `backend/app/core/exceptions.py` (`GroundworkError` audit-context fields)
- `backend/app/core/pagination.py` (relocated from `app/utils/pagination.py`)
- `backend/app/services/audit_service.py` (`AuditWriter`, `_AuditScope`)
- `backend/app/main.py` (route-level failure-audit handler)
- `backend/app/routers/__init__.py` (convention comment block)
- `backend/docs/conventions.md`
- `backend/tests/test_services/test_audit_writer.py`
- `backend/tests/test_cross_cutting/test_stub_dependencies.py`

## Non-goals

- Domain vertical slices (Organization, EntityType, etc.) — separately owned by TASK-009, TASK-010, etc.
- Real auth middleware (TASK-014) or real permission resolution (TASK-015).
