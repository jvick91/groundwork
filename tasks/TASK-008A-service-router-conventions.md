# TASK-008A: Service & Router Layer Conventions

**Status:** Not started
**Spec sections:** SPEC-007 §12.2 (layer responsibilities), §12.3 (dependency injection)
**ADRs:** ADR-002 (FK-only, explicit queries)
**Depends on:** TASK-002, TASK-003, TASK-004, TASK-006, TASK-007, TASK-008

## Objective

Establish the service and router conventions by implementing the Organization CRUD as the reference vertical slice. All subsequent domain tasks will follow the patterns defined here. This task produces the first working router, the first working service, the first domain Pydantic schemas, and the audit integration pattern — all exercised by tests.

## Conventions to Establish

### Router pattern
- One router file per domain under `app/routers/`, registered in `main.py`
- Routes never import SQLAlchemy, never contain business logic, never access DB directly
- Permission checked via `Depends(require_permission("permission.slug"))` (stubbed until TASK-014)
- Org context + actor identity from auth dependency (stubbed until TASK-014)
- Routes call service functions and return Pydantic response models

### Service pattern
- Plain async functions in `app/services/` (not classes — no state to manage)
- Signature: `async def create_X(db: AsyncSession, org_id: UUID, data: CreateSchema) -> Model`
- `db: AsyncSession` passed in from router's `get_db` dependency — service does not create its own session
- Service owns all business rules; raises domain exceptions from `app.core.exceptions`
- Audit logging called inside the same session before the implicit commit

### Audit integration pattern
- `await audit_service.log_action(db, org_id=..., actor_id=..., action="created", resource_type="Organization", resource_id=..., previous_state=None, next_state={...})`
- PHI field exclusion list applied automatically by audit service before writing snapshots
- Audit write uses the same `db` session — if it fails, the business operation rolls back

### Org-scoped query pattern
- All queries that return domain data add `.where(Model.organization_id == org_id)`
- Soft-deleted records excluded by default: `.where(Model.deleted_at.is_(None))`
- These two filters are applied consistently in every service list/get function

## Acceptance Criteria

- [ ] `backend/app/routers/eav.py` exists with Organization CRUD endpoints registered in main.py
- [ ] `backend/app/services/eav_service.py` exists with create, get, list, update functions for Organization
- [ ] `backend/app/schemas/eav.py` exists with OrganizationCreate, OrganizationUpdate, OrganizationResponse schemas
- [ ] Router calls service, service calls audit — full vertical slice working end-to-end
- [ ] Auth dependency is stubbed (hardcoded test identity) until TASK-014 replaces it
- [ ] Audit service (from TASK-006) is called for every state change
- [ ] Test: Organization CRUD happy path via httpx client
- [ ] Test: Audit log entry created on Organization create
- [ ] All subsequent domain tasks can follow this pattern without inventing new conventions

## Files

- `backend/app/routers/eav.py` (Organization endpoints — reference router)
- `backend/app/services/eav_service.py` (Organization service — reference service)
- `backend/app/schemas/eav.py` (Organization schemas — reference schemas)
- `backend/app/main.py` (router registration)
- `backend/tests/test_eav/test_organizations.py`

## Non-goals

- EntityType, EntityAttribute, EntityInstance APIs (TASK-010, TASK-011)
- Real auth middleware (TASK-014)
- Any domain beyond Organization
