"""
Direct unit tests for ``EntityAttributeService``.

Covers create / get / list / update / delete with the system-type
protection rule for attribute deletion.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ResourceLockedError
from app.enums.eav import FieldType
from app.models.eav import EntityType, Organization
from app.schemas.eav import EntityAttributeCreate, EntityAttributeUpdate
from app.schemas.pagination import PaginationParams
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.entity_attribute_service import EntityAttributeService

pytestmark = pytest.mark.asyncio


async def _make_org(session: AsyncSession) -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name="EA Service Tenant",
        timezone="UTC",
        is_active=True,
    )
    session.add(org)
    await session.flush()
    return org


async def _make_type(
    session: AsyncSession,
    org_id: uuid.UUID | None,
    *,
    is_system: bool = False,
    slug: str | None = None,
) -> EntityType:
    et = EntityType(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Test Type",
        slug=slug or f"type-{uuid.uuid4().hex[:6]}",
        is_system_type=is_system,
        is_person_subtype=False,
    )
    session.add(et)
    await session.flush()
    return et


def _service(session: AsyncSession, tenant_id: uuid.UUID) -> EntityAttributeService:
    audit = AuditWriter(session, _AuditScope(org_id=tenant_id, actor_id=None))
    return EntityAttributeService(
        session=session,
        audit=audit,
        tenant_id=tenant_id,
        actor_id=None,
    )


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_persists_attribute(db_session: AsyncSession):
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    service = _service(db_session, org.id)

    ea = await service.create(
        et.id,
        EntityAttributeCreate(
            name="license_number",
            display_name="License Number",
            field_type=FieldType.TEXT,
            is_required=True,
            display_order=0,
        ),
    )
    assert ea.id is not None
    assert ea.entity_type_id == et.id
    assert ea.name == "license_number"
    assert ea.is_required is True


async def test_create_on_system_type_succeeds(db_session: AsyncSession):
    """System types are extensible — new attributes can be added."""
    org = await _make_org(db_session)
    sys_et = await _make_type(db_session, None, is_system=True)
    service = _service(db_session, org.id)

    ea = await service.create(
        sys_et.id,
        EntityAttributeCreate(
            name="custom_extra",
            display_name="Custom Extra",
            field_type=FieldType.TEXT,
        ),
    )
    assert ea.entity_type_id == sys_et.id


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_returns_attribute_in_scope(db_session: AsyncSession):
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    service = _service(db_session, org.id)
    created = await service.create(
        et.id,
        EntityAttributeCreate(
            name="field1",
            display_name="Field 1",
            field_type=FieldType.TEXT,
        ),
    )
    fetched = await service.get(created.id, et.id)
    assert fetched.id == created.id


async def test_get_raises_not_found_when_attr_belongs_to_different_type(
    db_session: AsyncSession,
):
    """Cross-type access is blocked (NotFoundError, not 200)."""
    org = await _make_org(db_session)
    type_a = await _make_type(db_session, org.id)
    type_b = await _make_type(db_session, org.id)
    service = _service(db_session, org.id)
    attr_in_a = await service.create(
        type_a.id,
        EntityAttributeCreate(
            name="cross",
            display_name="Cross",
            field_type=FieldType.TEXT,
        ),
    )

    with pytest.raises(NotFoundError):
        await service.get(attr_in_a.id, type_b.id)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


async def test_list_returns_attributes_for_type(db_session: AsyncSession):
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    service = _service(db_session, org.id)

    for i in range(3):
        await service.create(
            et.id,
            EntityAttributeCreate(
                name=f"attr_{i}",
                display_name=f"Attr {i}",
                field_type=FieldType.TEXT,
                display_order=i,
            ),
        )

    items, _meta = await service.list(et.id, PaginationParams(limit=10))
    assert len(items) == 3
    assert all(it.entity_type_id == et.id for it in items)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_applies_partial_fields(db_session: AsyncSession):
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    service = _service(db_session, org.id)
    created = await service.create(
        et.id,
        EntityAttributeCreate(
            name="upd",
            display_name="Old Display",
            field_type=FieldType.TEXT,
        ),
    )

    updated = await service.update(
        created.id,
        et.id,
        EntityAttributeUpdate(display_name="New Display", is_required=True),
    )
    assert updated.display_name == "New Display"
    assert updated.is_required is True
    # Untouched fields preserved
    assert updated.name == "upd"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_removes_attribute_on_custom_type(db_session: AsyncSession):
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    service = _service(db_session, org.id)
    created = await service.create(
        et.id,
        EntityAttributeCreate(
            name="del",
            display_name="To Delete",
            field_type=FieldType.TEXT,
        ),
    )

    await service.delete(created.id, et)

    with pytest.raises(NotFoundError):
        await service.get(created.id, et.id)


async def test_delete_attribute_on_system_type_raises_resource_locked(
    db_session: AsyncSession,
):
    """Attributes on system types cannot be deleted (SPEC-001 §4)."""
    org = await _make_org(db_session)
    sys_et = await _make_type(db_session, None, is_system=True)
    service = _service(db_session, org.id)
    created = await service.create(
        sys_et.id,
        EntityAttributeCreate(
            name="seed_field",
            display_name="Seed Field",
            field_type=FieldType.TEXT,
        ),
    )

    with pytest.raises(ResourceLockedError, match="cannot be deleted"):
        await service.delete(created.id, sys_et)
