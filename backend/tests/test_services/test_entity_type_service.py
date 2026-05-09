"""
Direct unit tests for ``EntityTypeService`` (ADR-009).

Exercises the create / get / list / update / delete methods directly with a
real session, real repository, and real ``AuditWriter``. Also exercises the
system-type guard via ``EntityType.assert_mutable``.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceLockedError, SlugNotFoundError
from app.models.eav import EntityType, Organization
from app.repositories.entity_type_repository import EntityTypeRepository
from app.schemas.eav import EntityTypeCreate, EntityTypeUpdate
from app.schemas.pagination import PaginationParams
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.entity_type_service import EntityTypeService

pytestmark = pytest.mark.asyncio


async def _make_org(session: AsyncSession) -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        name="ET Service Tenant",
        timezone="UTC",
        is_active=True,
    )
    session.add(org)
    await session.flush()
    return org


async def _make_system_type(session: AsyncSession, slug: str) -> EntityType:
    et = EntityType(
        id=uuid.uuid4(),
        organization_id=None,
        name=slug.capitalize(),
        slug=slug,
        is_system_type=True,
        is_person_subtype=True,
    )
    session.add(et)
    await session.flush()
    return et


def _service(session: AsyncSession, tenant_id: uuid.UUID) -> EntityTypeService:
    audit = AuditWriter(session, _AuditScope(org_id=tenant_id, actor_id=None))
    return EntityTypeService(
        repo=EntityTypeRepository(session),
        audit=audit,
        tenant_id=tenant_id,
        actor_id=None,
    )


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_persists_custom_type_with_org_scope(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    et = await service.create(EntityTypeCreate(name="Nutritionist", slug="nutritionist"))
    assert et.id is not None
    assert et.organization_id == org.id
    assert et.is_system_type is False


async def test_create_rejects_system_reserved_slug(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    with pytest.raises(ConflictError, match="system-reserved"):
        await service.create(EntityTypeCreate(name="My Provider", slug="provider"))


async def test_create_rejects_intra_org_duplicate_slug(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    await service.create(EntityTypeCreate(name="First", slug="dietitian"))
    with pytest.raises(ConflictError, match="already exists"):
        await service.create(EntityTypeCreate(name="Second", slug="dietitian"))


# ---------------------------------------------------------------------------
# get_by_slug
# ---------------------------------------------------------------------------


async def test_get_by_slug_returns_existing(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    created = await service.create(EntityTypeCreate(name="Coach", slug="coach"))
    fetched = await service.get_by_slug("coach")
    assert fetched.id == created.id


async def test_get_by_slug_unknown_raises_slug_not_found(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    with pytest.raises(SlugNotFoundError):
        await service.get_by_slug("ghost-slug")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


async def test_list_includes_system_and_org_custom_types(db_session: AsyncSession):
    org = await _make_org(db_session)
    await _make_system_type(db_session, f"sys-{uuid.uuid4().hex[:6]}")
    service = _service(db_session, org.id)
    await service.create(EntityTypeCreate(name="Custom", slug=f"cust-{uuid.uuid4().hex[:6]}"))

    items, meta = await service.list(PaginationParams(limit=100))
    assert meta.limit == 100
    assert len(items) >= 2
    has_system = any(it.is_system_type for it in items)
    has_custom = any(not it.is_system_type and it.organization_id == org.id for it in items)
    assert has_system and has_custom


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_applies_partial_fields(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    await service.create(EntityTypeCreate(name="Old Name", slug="rename-me"))

    updated = await service.update("rename-me", EntityTypeUpdate(name="New Name"))
    assert updated.name == "New Name"
    assert updated.slug == "rename-me"


async def test_update_can_change_slug_when_unique(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    await service.create(EntityTypeCreate(name="Slug Mover", slug="old-slug"))

    updated = await service.update("old-slug", EntityTypeUpdate(slug="new-slug"))
    assert updated.slug == "new-slug"


async def test_update_blocks_slug_collision(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    await service.create(EntityTypeCreate(name="A", slug="taken-slug"))
    await service.create(EntityTypeCreate(name="B", slug="will-collide"))

    with pytest.raises(ConflictError, match="already exists"):
        await service.update("will-collide", EntityTypeUpdate(slug="taken-slug"))


async def test_update_on_system_type_raises_resource_locked(db_session: AsyncSession):
    org = await _make_org(db_session)
    sys_slug = f"sys-{uuid.uuid4().hex[:6]}"
    await _make_system_type(db_session, sys_slug)
    service = _service(db_session, org.id)

    with pytest.raises(ResourceLockedError, match="renamed or modified"):
        await service.update(sys_slug, EntityTypeUpdate(name="impossible"))


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_removes_custom_type(db_session: AsyncSession):
    org = await _make_org(db_session)
    service = _service(db_session, org.id)
    await service.create(EntityTypeCreate(name="Temp", slug="temp-type"))

    await service.delete("temp-type")

    with pytest.raises(SlugNotFoundError):
        await service.get_by_slug("temp-type")


async def test_delete_on_system_type_raises_resource_locked(db_session: AsyncSession):
    org = await _make_org(db_session)
    sys_slug = f"sys-{uuid.uuid4().hex[:6]}"
    await _make_system_type(db_session, sys_slug)
    service = _service(db_session, org.id)

    with pytest.raises(ResourceLockedError, match="cannot be deleted"):
        await service.delete(sys_slug)
