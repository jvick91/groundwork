"""
Service layer for EAV domain entities.

Organization is the root tenant record. All state-changing operations write
an AuditLog entry and invoke registered on_organization_created hooks inside
the same transaction (BR-07). The ``get_db`` dependency owns commit/rollback;
this layer never commits directly.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.models import Organization
from app.schemas.eav import OrganizationCreate, OrganizationUpdate
from app.schemas.schemas import PaginationMeta, PaginationParams
from app.services import audit_service, organization_hooks
from app.utils.pagination import paginate

_SORT_FIELDS = {
    "created_at": Organization.created_at,
    "updated_at": Organization.updated_at,
    "name": Organization.name,
}


def _org_snapshot(org: Organization) -> dict[str, Any]:
    """Return a serialisable snapshot of an Organization for audit logging."""
    return {
        "id": str(org.id),
        "name": org.name,
        "npi_number": org.npi_number,
        "tax_id": org.tax_id,
        "phone": org.phone,
        "address_line1": org.address_line1,
        "address_line2": org.address_line2,
        "city": org.city,
        "state": org.state,
        "postal_code": org.postal_code,
        "country": org.country,
        "timezone": org.timezone,
        "is_active": org.is_active,
    }


async def create_organization(
    db: AsyncSession,
    *,
    actor_id: UUID | None,
    data: OrganizationCreate,
) -> Organization:
    """Create a new Organization tenant.

    Order of writes (same transaction):
    1. Organization INSERT + flush (to obtain the PK).
    2. AuditLog INSERT (BR-07).
    3. on_organization_created hooks (TASK-029 / TASK-032 extension point).

    Any failure rolls back all three via ``get_db``.
    """
    org = Organization(
        name=data.name,
        npi_number=data.npi_number,
        tax_id=data.tax_id,
        phone=data.phone,
        address_line1=data.address_line1,
        address_line2=data.address_line2,
        city=data.city,
        state=data.state,
        postal_code=data.postal_code,
        country=data.country,
        timezone=data.timezone,
        is_active=True,
        created_at=datetime.now(tz=UTC),
    )
    db.add(org)
    await db.flush()

    await audit_service.log_action(
        db,
        org_id=org.id,
        actor_id=actor_id,
        action="create",
        resource_type="Organization",
        resource_id=org.id,
        next_state=_org_snapshot(org),
    )

    await organization_hooks.on_organization_created(db, org.id)

    return org


async def get_organization(
    db: AsyncSession,
    org_id: UUID,
) -> Organization:
    """Return an Organization by primary key, raising ``NotFoundError`` if absent."""
    result = await db.get(Organization, org_id)
    if result is None:
        raise NotFoundError("Organization", org_id)
    return result


async def list_organizations(
    db: AsyncSession,
    *,
    params: PaginationParams,
) -> tuple[list[Organization], PaginationMeta]:
    """Return a paginated list of all organizations."""
    stmt = select(Organization)
    return await paginate(
        db,
        stmt,
        params=params,
        sort_fields=_SORT_FIELDS,
        id_col=Organization.id,
    )


async def update_organization(
    db: AsyncSession,
    *,
    org_id: UUID,
    actor_id: UUID | None,
    data: OrganizationUpdate,
) -> Organization:
    """Apply a partial update to an Organization and write an audit entry.

    Only fields that are explicitly set in the request body are applied
    (``model_dump(exclude_unset=True)`` semantics).
    """
    org = await get_organization(db, org_id)
    previous = _org_snapshot(org)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(org, field, value)

    org.updated_at = datetime.now(tz=UTC)
    await db.flush()

    await audit_service.log_action(
        db,
        org_id=org.id,
        actor_id=actor_id,
        action="update",
        resource_type="Organization",
        resource_id=org.id,
        previous_state=previous,
        next_state=_org_snapshot(org),
    )

    return org
