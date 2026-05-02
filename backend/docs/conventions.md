# Service & Router Conventions

This is the contract every domain (Organization, Person, Session, ClinicalNote, …) must follow. Source: SPEC-007 §12; established by TASK-008A; first exercised by TASK-009.

If you are about to add a new endpoint, check it against the four patterns below before writing code.

## 1. Router pattern

- One router file per domain under [backend/app/routers/](../app/routers/), registered via `app.include_router()` in `main.py`.
- Routers **never** import SQLAlchemy, **never** contain business logic, **never** open a session.
- Permission checks: `Depends(require_permission("resource.action"))`.
- Identity + tenant: `current_person` and `current_org` dependencies — both return dicts with stable keys (see `app.core.security`).
- Response: a Pydantic model from `app.schemas.<domain>`, never the ORM instance.

```python
@router.post(
    "",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("organization.create"))],
)
async def create_organization(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    org: dict = Depends(current_org),
    actor: dict = Depends(current_person),
) -> OrganizationRead:
    result = await org_service.create_organization(
        db, org_id=org["id"], actor_id=actor["id"], data=body,
    )
    return OrganizationRead.model_validate(result)
```

## 2. Service pattern

- Plain async functions in [backend/app/services/](../app/services/) — **not classes**, because there is no state to manage.
- Signature shape: `async def create_X(db: AsyncSession, *, org_id: UUID, actor_id: UUID | None, data: <Schema>) -> Model`.
- The router passes `db` in via `Depends(get_db)`. The service **never** creates its own session. Routes own session lifecycle; services own business rules.
- Services raise the domain exceptions in `app.core.exceptions` — never `HTTPException` directly.
- Services do not commit. The `get_db` dependency commits on successful return and rolls back on any exception (`backend/app/core/dependencies.py`).

## 3. Audit integration pattern

Every state-changing operation writes an AuditLog row in the **same transaction** as the business write (BR-07; SPEC-006 §4). Use the shared helper rather than re-implementing the dance:

```python
from app.services.common import call_service_with_audit

async def create_organization(
    db: AsyncSession,
    *,
    org_id: UUID,
    actor_id: UUID | None,
    data: OrganizationCreate,
) -> Organization:
    async def _write() -> Organization:
        org = Organization(name=data.name, ...)
        db.add(org)
        await db.flush()
        return org

    return await call_service_with_audit(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="create",
        resource_type="Organization",
        resource_id_getter=lambda o: o.id,
        operation=_write,
        next_state_getter=lambda o: {"name": o.name, ...},
    )
```

The helper:
- runs the business operation,
- writes the audit row using the same session,
- rolls the session back if either step raises,
- returns the operation result so the router can shape a response.

PHI field exclusion is automatic: `audit_service.log_action` strips every name in `PHI_EXCLUDED_FIELDS` from the snapshots before the row is written. Callers must never filter PHI themselves; the centralized list is the single source of truth.

## 4. Org-scoped query pattern

Every list/get query that returns domain data must apply two filters:

- Tenant scope: `.where(<Model>.organization_id == org_id)`
- Soft-delete exclusion: `.where(<Model>.deleted_at.is_(None))`

Apply both consistently — there is no convenience method that hides them, because making them explicit at the query site is the point. TASK-015 (permission resolution) will layer row-level filtering on top of this baseline; the org-scope filter remains the always-on tenant boundary.

## Pagination

List endpoints use the cursor-based helper from [backend/app/utils/pagination.py](../app/utils/pagination.py). Build a `select()` with the org/soft-delete filters, then hand it to `paginate(...)` along with a sort-field allow-list. See SPEC-007 §5–§6 for the wire contract; see TASK-009 for the canonical example once it lands.

## Auth stubs (Phase 1 only)

While `settings.auth_stub_enabled = True`, the auth dependencies short-circuit:

- `get_auth_context` returns a fixed test identity. `person_id` is `None` (system actor — `audit_logs.actor_person_id` is nullable per SPEC-006 §7, and there are no `people` rows to FK against until TASK-012 lands). `organization_id` is a fixed UUID; `auth_subject` is a fixed string.
- `require_permission(slug)` allow-lists every check.
- `current_person` / `current_org` return dicts with the documented keys. Under the stub, `current_person()["id"]` is `None`.

Routers should still wire these dependencies as if they were real. TASK-014 (auth middleware) and TASK-015 (permission resolution) will swap the implementation in one place; the router and service code never changes.
