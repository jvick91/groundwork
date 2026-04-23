# TASK-008A: Service & Router Layer Conventions (Shared Plumbing)

**Status:** Not started
**Spec sections:** SPEC-007 §12.2 (layer responsibilities), §12.3 (dependency injection)
**ADRs:** ADR-002 (FK-only, explicit queries)
**Depends on:** TASK-002, TASK-003, TASK-004, TASK-006, TASK-007, TASK-008

## Objective

Produce the shared plumbing every domain router/service will consume — and nothing else. This task lands the `get_db` dependency, the stubbed `current_person` / `current_org` / `require_permission` dependencies that TASK-014/015 will replace, the `call_service_with_audit` helper that wires the audit service into service functions, the pagination helper wiring from TASK-004, and a short convention doc. No domain endpoints, no domain models, no domain schemas are produced here. TASK-009 is the first consumer and will validate that the conventions are sound by implementing the first vertical slice (Organization).

## Conventions to Establish

### Router pattern
- One router file per domain under `app/routers/`, registered in `main.py`
- Routes never import SQLAlchemy, never contain business logic, never access DB directly
- Permission checked via `Depends(require_permission("permission.slug"))` (stub returns allow until TASK-014/015 land the real implementation)
- Org context + actor identity from auth dependency (stub returns a fixed test identity until TASK-014 lands)
- Routes call service functions and return Pydantic response models

### Service pattern
- Plain async functions in `app/services/` (not classes — no state to manage)
- Signature: `async def create_X(db: AsyncSession, org_id: UUID, data: CreateSchema) -> Model`
- `db: AsyncSession` passed in from router's `get_db` dependency — service does not create its own session
- Service owns all business rules; raises domain exceptions from `app.core.exceptions`
- Audit logging called inside the same session before the implicit commit

### Audit integration pattern
- `await audit_service.log_action(db, org_id=..., actor_id=..., action="created", resource_type="<Model>", resource_id=..., previous_state=None, next_state={...})`
- PHI field exclusion list applied automatically by audit service before writing snapshots
- Audit write uses the same `db` session — if it fails, the business operation rolls back

### Org-scoped query pattern
- All queries that return domain data add `.where(Model.organization_id == org_id)`
- Soft-deleted records excluded by default: `.where(Model.deleted_at.is_(None))`
- These two filters are applied consistently in every service list/get function

## Acceptance Criteria

- [ ] `app/core/dependencies.py` exports `get_db`, `current_person` (stub returning a fixed test Person shape until TASK-014), `current_org` (stub returning a fixed test Organization context until TASK-014), and `require_permission(slug)` (stub that allow-lists until TASK-015)
- [ ] Stubs are feature-flagged via `settings.AUTH_STUB_ENABLED` so TASK-014/015 can flip the flag off in one place
- [ ] `app/services/common.py` (or similar) exports a `call_service_with_audit(...)` helper that encapsulates the audit wrap pattern, so services don't re-implement the try/commit/rollback dance
- [ ] Pagination helpers from TASK-004 are exposed via a single importable surface (e.g. `app.utils.pagination.paginate_query`) that every list endpoint will use
- [ ] `app/routers/__init__.py` documents the required router shape (one comment block showing the expected imports, `Depends` wiring, and response model conventions) — no domain routers are registered in this task
- [ ] `docs/conventions.md` (or a README inside `app/`) written with the four patterns above in ~1 page, referenced from each future domain task
- [ ] Tests: `tests/test_core/test_dependencies.py` — verifies each stub dependency returns the expected shape and that `require_permission` allow-lists while the flag is on; verifies `call_service_with_audit` rolls back the business write when the audit write raises
- [ ] No domain endpoints, models, schemas, or tables are introduced by this task
- [ ] Stub-dependency shape tests: `tests/test_cross_cutting/test_stub_dependencies.py` asserts `current_person` returns a dict with `id`, `email`, `is_active`; `current_org` returns a dict with `id`, `name`, `timezone`; `require_permission("any.slug")` returns an allow decision while `AUTH_STUB_ENABLED=true`. Tests fail loudly if the stub shape drifts before TASK-014 wires the real dependencies.

## Files

- `backend/app/core/dependencies.py`
- `backend/app/core/settings.py` (add `AUTH_STUB_ENABLED` flag)
- `backend/app/services/common.py`
- `backend/app/utils/pagination.py` (wire the helper surface created in TASK-004)
- `backend/app/routers/__init__.py` (convention comment block)
- `backend/docs/conventions.md`
- `backend/tests/test_core/test_dependencies.py`

## Non-goals

- Organization model, schema, service, router, migration, or tests — all owned by TASK-009 as the first consumer of these conventions
- EntityType, EntityAttribute, EntityInstance APIs (TASK-010, TASK-011-series)
- Real auth middleware (TASK-014) or real permission resolution (TASK-015)
- Any domain vertical slice
