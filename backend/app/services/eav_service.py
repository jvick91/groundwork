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

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ResourceLockedError,
    SlugNotFoundError,
)
from app.models.models import EntityAttribute, EntityType, Organization
from app.schemas.eav import (
    EntityAttributeCreate,
    EntityAttributeUpdate,
    EntityTypeCreate,
    EntityTypeUpdate,
    OrganizationCreate,
    OrganizationUpdate,
)
from app.schemas.schemas import PaginationMeta, PaginationParams
from app.services import audit_service, organization_hooks
from app.utils.pagination import paginate

# System slugs are globally reserved — no org may claim them for a custom type.
_SYSTEM_SLUGS: frozenset[str] = frozenset({"provider", "client", "admin"})

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
        "address": org.address,
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
        address=data.address,
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


# ---------------------------------------------------------------------------
# EntityType — sort fields
# ---------------------------------------------------------------------------

_ET_SORT_FIELDS = {
    "created_at": EntityType.created_at,
    "name": EntityType.name,
    "slug": EntityType.slug,
}


def _et_snapshot(et: EntityType) -> dict[str, Any]:
    return {
        "id": str(et.id),
        "organization_id": str(et.organization_id) if et.organization_id else None,
        "name": et.name,
        "slug": et.slug,
        "is_system_type": et.is_system_type,
        "is_person_subtype": et.is_person_subtype,
    }


async def _assert_slug_available(
    db: AsyncSession,
    slug: str,
    org_id: UUID | None,
    exclude_id: UUID | None = None,
) -> None:
    """Raise ConflictError if the slug is already taken within the org scope.

    System slugs (provider, client, admin) are globally reserved — no org
    may claim them for a custom type.
    """
    if slug in _SYSTEM_SLUGS:
        raise ConflictError(
            f"Slug '{slug}' is a system-reserved slug and cannot be used for a custom type.",
            details=[{"slug": slug}],
        )

    # Check for a duplicate within the same org (NULL org_id = system scope).
    stmt = select(EntityType).where(EntityType.slug == slug)
    if org_id is None:
        stmt = stmt.where(EntityType.organization_id.is_(None))
    else:
        stmt = stmt.where(EntityType.organization_id == org_id)
    if exclude_id is not None:
        stmt = stmt.where(EntityType.id != exclude_id)

    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise ConflictError(
            f"An EntityType with slug '{slug}' already exists in this organization.",
            details=[{"slug": slug}],
        )


async def list_entity_types(
    db: AsyncSession,
    *,
    params: PaginationParams,
    org_id: UUID | None = None,
) -> tuple[list[EntityType], PaginationMeta]:
    """Return a cursor-paginated list of EntityTypes.

    Returns system types (organization_id IS NULL) plus any custom types
    belonging to the given org.
    """
    from sqlalchemy import or_

    stmt = select(EntityType)
    if org_id is not None:
        stmt = stmt.where(
            or_(
                EntityType.organization_id.is_(None),
                EntityType.organization_id == org_id,
            )
        )
    return await paginate(
        db,
        stmt,
        params=params,
        sort_fields=_ET_SORT_FIELDS,
        id_col=EntityType.id,
    )


async def get_entity_type_by_slug(db: AsyncSession, slug: str) -> EntityType:
    """Return an EntityType by slug, raising SlugNotFoundError if absent."""
    stmt = select(EntityType).where(EntityType.slug == slug)
    result = await db.execute(stmt)
    et = result.scalar_one_or_none()
    if et is None:
        raise SlugNotFoundError("EntityType", slug)
    return et


async def create_entity_type(
    db: AsyncSession,
    *,
    org_id: UUID | None,
    actor_id: UUID | None,
    data: EntityTypeCreate,
) -> EntityType:
    """Create a custom EntityType for the given organization.

    System slugs and duplicate slugs within the same org are rejected with 409.
    Callers must gate on ``settings.custom_entity_types_enabled`` before calling
    (router layer responsibility).
    """
    await _assert_slug_available(db, data.slug, org_id)

    et = EntityType(
        organization_id=org_id,
        name=data.name,
        slug=data.slug,
        is_system_type=False,
        is_person_subtype=False,
        created_at=datetime.now(tz=UTC),
    )
    db.add(et)
    await db.flush()

    await audit_service.log_action(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="create",
        resource_type="EntityType",
        resource_id=et.id,
        next_state=_et_snapshot(et),
    )
    return et


async def update_entity_type(
    db: AsyncSession,
    *,
    slug: str,
    org_id: UUID | None,
    actor_id: UUID | None,
    data: EntityTypeUpdate,
) -> EntityType:
    """Partially update a custom EntityType.

    System types are locked (409). Slug renames are validated for uniqueness
    and will cascade to Permission rows in TASK-019; for now only the EntityType
    row is updated.
    """
    et = await get_entity_type_by_slug(db, slug)

    if et.is_system_type:
        raise ResourceLockedError("EntityType", "system types cannot be renamed or modified")

    previous = _et_snapshot(et)
    updates = data.model_dump(exclude_unset=True)

    new_slug = updates.get("slug")
    if new_slug is not None and new_slug != et.slug:
        await _assert_slug_available(db, new_slug, org_id, exclude_id=et.id)

    for field, value in updates.items():
        setattr(et, field, value)

    et.updated_at = datetime.now(tz=UTC)
    await db.flush()

    await audit_service.log_action(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="update",
        resource_type="EntityType",
        resource_id=et.id,
        previous_state=previous,
        next_state=_et_snapshot(et),
    )
    return et


async def delete_entity_type(
    db: AsyncSession,
    *,
    slug: str,
    org_id: UUID | None,
    actor_id: UUID | None,
) -> None:
    """Delete a custom EntityType.

    System types are locked (409). Does not cascade to EntityInstances or
    AttributeValues — callers should ensure the type is unused before deleting.
    """
    et = await get_entity_type_by_slug(db, slug)

    if et.is_system_type:
        raise ResourceLockedError("EntityType", "system types cannot be deleted")

    await audit_service.log_action(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="delete",
        resource_type="EntityType",
        resource_id=et.id,
        previous_state=_et_snapshot(et),
    )
    await db.delete(et)
    await db.flush()


# ---------------------------------------------------------------------------
# EntityAttribute
# ---------------------------------------------------------------------------

_EA_SORT_FIELDS = {
    "created_at": EntityAttribute.created_at,
    "display_order": EntityAttribute.display_order,
    "name": EntityAttribute.name,
}


def _ea_snapshot(ea: EntityAttribute) -> dict[str, Any]:
    return {
        "id": str(ea.id),
        "entity_type_id": str(ea.entity_type_id),
        "name": ea.name,
        "display_name": ea.display_name,
        "field_type": str(ea.field_type),
        "is_required": ea.is_required,
        "options": ea.options,
        "display_order": ea.display_order,
    }


async def get_entity_attribute(
    db: AsyncSession,
    *,
    attr_id: UUID,
    entity_type_id: UUID,
) -> EntityAttribute:
    """Return an EntityAttribute by PK, verifying it belongs to the given EntityType.

    Raises ``NotFoundError`` if the attribute is missing or scoped to a different type,
    preventing cross-type data exposure.
    """
    ea = await db.get(EntityAttribute, attr_id)
    if ea is None or ea.entity_type_id != entity_type_id:
        raise NotFoundError("EntityAttribute", attr_id)
    return ea


async def list_entity_attributes(
    db: AsyncSession,
    *,
    entity_type_id: UUID,
    params: PaginationParams,
) -> tuple[list[EntityAttribute], PaginationMeta]:
    """Return a cursor-paginated list of attributes for the given EntityType."""
    stmt = select(EntityAttribute).where(EntityAttribute.entity_type_id == entity_type_id)
    return await paginate(
        db,
        stmt,
        params=params,
        sort_fields=_EA_SORT_FIELDS,
        id_col=EntityAttribute.id,
    )


async def create_entity_attribute(
    db: AsyncSession,
    *,
    entity_type_id: UUID,
    org_id: UUID | None,
    actor_id: UUID | None,
    data: EntityAttributeCreate,
) -> EntityAttribute:
    """Add an attribute to an EntityType.

    Both system and custom types accept new attributes (SPEC-001 §4).
    Audit entry is written in the same transaction.
    """
    ea = EntityAttribute(
        entity_type_id=entity_type_id,
        name=data.name,
        display_name=data.display_name,
        field_type=data.field_type,
        is_required=data.is_required,
        options=data.options,
        display_order=data.display_order,
        created_at=datetime.now(tz=UTC),
    )
    db.add(ea)
    await db.flush()

    await audit_service.log_action(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="create",
        resource_type="EntityAttribute",
        resource_id=ea.id,
        next_state=_ea_snapshot(ea),
    )
    return ea


async def update_entity_attribute(
    db: AsyncSession,
    *,
    attr_id: UUID,
    entity_type_id: UUID,
    org_id: UUID | None,
    actor_id: UUID | None,
    data: EntityAttributeUpdate,
) -> EntityAttribute:
    """Partially update an EntityAttribute.

    Only provided fields are applied. Audit entry records previous and next state.
    """
    ea = await get_entity_attribute(db, attr_id=attr_id, entity_type_id=entity_type_id)
    previous = _ea_snapshot(ea)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(ea, field, value)

    ea.updated_at = datetime.now(tz=UTC)
    await db.flush()

    await audit_service.log_action(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="update",
        resource_type="EntityAttribute",
        resource_id=ea.id,
        previous_state=previous,
        next_state=_ea_snapshot(ea),
    )
    return ea


async def delete_entity_attribute(
    db: AsyncSession,
    *,
    attr_id: UUID,
    entity_type_id: UUID,
    org_id: UUID | None,
    actor_id: UUID | None,
) -> None:
    """Delete an EntityAttribute.

    Attributes on system types are fully protected from deletion (SPEC-001 §4):
    seed attributes must not be removed, and for MVP correctness the same
    protection extends to any attribute on a system type regardless of when it
    was added.  Custom-type attributes may be deleted freely.
    """
    ea = await get_entity_attribute(db, attr_id=attr_id, entity_type_id=entity_type_id)

    # Load parent type to check system-type protection.
    parent = await db.get(EntityType, entity_type_id)
    if parent is not None and parent.is_system_type:
        raise ResourceLockedError(
            "EntityAttribute",
            "attributes on system types cannot be deleted",
        )

    await audit_service.log_action(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="delete",
        resource_type="EntityAttribute",
        resource_id=ea.id,
        previous_state=_ea_snapshot(ea),
    )
    await db.delete(ea)
    await db.flush()
