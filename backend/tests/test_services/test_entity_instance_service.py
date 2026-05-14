"""
Integration tests for EntityInstanceService (TASK-011C).

All tests use a real database session and cover the SPEC-001 §9 test table:

  - Soft-deleted instances excluded from list (BR-05)
  - Multi-tenancy isolation on list (org filter)
  - Required-field enforcement on create / update (422)
  - Wrong field_type value on create (422)
  - Enum value not in options on create (422)
  - FK type-slug mismatch on create (422)
  - FK referenced instance soft-deleted (422)
  - Audit log written on update and delete
  - Audit snapshot for AttributeValue NEVER contains ``value`` field
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.enums.eav import FieldType
from app.models.compliance import AuditLog
from app.models.eav import EntityAttribute, EntityType, Organization
from app.schemas.eav import EntityInstanceCreate, EntityInstanceUpdate
from app.schemas.pagination import PaginationParams
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.entity_instance_service import EntityInstanceService

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, *, name: str = "Test Org") -> Organization:
    org = Organization(id=uuid.uuid4(), name=name, timezone="UTC", is_active=True)
    session.add(org)
    await session.flush()
    return org


async def _make_type(
    session: AsyncSession,
    org_id: uuid.UUID | None = None,
    *,
    slug: str | None = None,
    is_system: bool = False,
    is_person_subtype: bool = False,
) -> EntityType:
    et = EntityType(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Test Type",
        slug=slug or f"type-{uuid.uuid4().hex[:6]}",
        is_system_type=is_system,
        is_person_subtype=is_person_subtype,
    )
    session.add(et)
    await session.flush()
    return et


async def _make_attr(
    session: AsyncSession,
    entity_type_id: uuid.UUID,
    *,
    name: str,
    field_type: FieldType = FieldType.TEXT,
    is_required: bool = False,
    options: Any = None,
) -> EntityAttribute:
    ea = EntityAttribute(
        id=uuid.uuid4(),
        entity_type_id=entity_type_id,
        name=name,
        display_name=name.replace("_", " ").title(),
        field_type=field_type,
        is_required=is_required,
        options=options,
        display_order=0,
    )
    session.add(ea)
    await session.flush()
    return ea


def _service(session: AsyncSession, tenant_id: uuid.UUID) -> EntityInstanceService:
    audit = AuditWriter(session, _AuditScope(org_id=tenant_id, actor_id=None))
    return EntityInstanceService(session=session, audit=audit, tenant_id=tenant_id, actor_id=None)


# ---------------------------------------------------------------------------
# create — happy path
# ---------------------------------------------------------------------------


async def test_create_persists_instance(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(db_session, et.id, name="notes_field", field_type=FieldType.TEXT)

    service = _service(db_session, org.id)
    result = await service.create(et.slug, EntityInstanceCreate(values={"notes_field": "hello"}))

    assert result.instance.organization_id == org.id
    assert result.instance.entity_type_id == et.id
    assert result.instance.is_active is True
    assert result.values == {"notes_field": "hello"}


async def test_create_with_no_values(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    result = await service.create(et.slug, EntityInstanceCreate())

    assert result.instance.id is not None
    assert result.values == {}


async def test_create_writes_entity_instance_audit(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    result = await service.create(et.slug, EntityInstanceCreate())

    audit_result = await db_session.execute(
        __import__("sqlalchemy", fromlist=["select"])
        .select(AuditLog)
        .where(
            AuditLog.resource_type == "EntityInstance",
            AuditLog.resource_id == result.instance.id,
            AuditLog.action == "create",
        )
    )
    row = audit_result.scalar_one_or_none()
    assert row is not None


async def test_create_attribute_value_audit_excludes_value_field(
    db_session: AsyncSession,
) -> None:
    """SPEC-001 §7: AttributeValue audit snapshots must never contain the value."""
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(db_session, et.id, name="secret", field_type=FieldType.TEXT)

    service = _service(db_session, org.id)
    await service.create(et.slug, EntityInstanceCreate(values={"secret": "sensitive data"}))

    from sqlalchemy import select as sa_select

    audit_result = await db_session.execute(
        sa_select(AuditLog).where(AuditLog.resource_type == "AttributeValue")
    )
    rows = audit_result.scalars().all()
    assert rows, "expected at least one AttributeValue audit row"
    for row in rows:
        for snapshot in (row.previous_state, row.next_state):
            if snapshot is not None:
                assert (
                    "value" not in snapshot
                ), f"'value' must never appear in AttributeValue audit snapshot: {snapshot}"


# ---------------------------------------------------------------------------
# create — validation failures
# ---------------------------------------------------------------------------


async def test_create_missing_required_field_returns_422(db_session: AsyncSession) -> None:
    """SPEC-001 §9 — test_create_instance_missing_required_field_returns_422"""
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(db_session, et.id, name="mandatory", is_required=True)

    service = _service(db_session, org.id)
    with pytest.raises(DomainValidationError) as exc:
        await service.create(et.slug, EntityInstanceCreate())
    assert "mandatory" in exc.value.message


async def test_create_value_wrong_type_returns_422(db_session: AsyncSession) -> None:
    """SPEC-001 §9 — test_create_value_wrong_type_returns_422"""
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(db_session, et.id, name="birth_date", field_type=FieldType.DATE)

    service = _service(db_session, org.id)
    with pytest.raises(DomainValidationError) as exc:
        await service.create(et.slug, EntityInstanceCreate(values={"birth_date": "not-a-date"}))
    assert "birth_date" in exc.value.message
    assert exc.value.status_code == 422


async def test_create_enum_value_not_in_options_returns_422(db_session: AsyncSession) -> None:
    """SPEC-001 §9 — test_create_enum_value_not_in_options_returns_422"""
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(
        db_session,
        et.id,
        name="status",
        field_type=FieldType.ENUM,
        options=["new", "active", "closed"],
    )

    service = _service(db_session, org.id)
    with pytest.raises(DomainValidationError) as exc:
        await service.create(et.slug, EntityInstanceCreate(values={"status": "unknown"}))
    assert "status" in exc.value.message
    assert exc.value.status_code == 422


async def test_create_unknown_attribute_returns_422(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    with pytest.raises(DomainValidationError) as exc:
        await service.create(et.slug, EntityInstanceCreate(values={"no_such_field": "value"}))
    assert "no_such_field" in exc.value.message


# ---------------------------------------------------------------------------
# FK field_type validation (full existence hook from TASK-011A + TASK-011C)
# ---------------------------------------------------------------------------


async def test_create_fk_value_references_valid_instance(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    target_type = await _make_type(db_session, org.id, slug="provider-type")
    source_type = await _make_type(db_session, org.id, slug="session-type")
    await _make_attr(
        db_session,
        source_type.id,
        name="provider_ref",
        field_type=FieldType.FK,
        options="provider-type",
    )

    # Create the target instance first
    provider_svc = _service(db_session, org.id)
    target = await provider_svc.create(target_type.slug, EntityInstanceCreate())

    # Now create source instance referencing the target
    source_svc = _service(db_session, org.id)
    result = await source_svc.create(
        source_type.slug,
        EntityInstanceCreate(values={"provider_ref": str(target.instance.id)}),
    )
    assert result.values["provider_ref"] == str(target.instance.id).lower()


async def test_create_fk_wrong_type_slug_returns_422(db_session: AsyncSession) -> None:
    """FK value points to an instance of the wrong EntityType slug."""
    org = await _make_org(db_session)
    client_type = await _make_type(db_session, org.id, slug="client-x")
    source_type = await _make_type(db_session, org.id, slug="session-x")
    await _make_attr(
        db_session,
        source_type.id,
        name="provider_ref",
        field_type=FieldType.FK,
        options="provider-x",  # expects provider, not client
    )

    client_svc = _service(db_session, org.id)
    client = await client_svc.create(client_type.slug, EntityInstanceCreate())

    source_svc = _service(db_session, org.id)
    with pytest.raises(DomainValidationError) as exc:
        await source_svc.create(
            source_type.slug,
            EntityInstanceCreate(values={"provider_ref": str(client.instance.id)}),
        )
    assert "provider_ref" in exc.value.message or "provider-x" in exc.value.message


async def test_create_fk_soft_deleted_instance_returns_422(db_session: AsyncSession) -> None:
    """FK value points to a soft-deleted EntityInstance."""
    org = await _make_org(db_session)
    target_type = await _make_type(db_session, org.id, slug="target-t")
    source_type = await _make_type(db_session, org.id, slug="source-t")
    await _make_attr(
        db_session,
        source_type.id,
        name="ref_field",
        field_type=FieldType.FK,
        options="target-t",
    )

    svc = _service(db_session, org.id)
    target = await svc.create(target_type.slug, EntityInstanceCreate())

    # Soft-delete the target
    await svc.delete(target_type.slug, target.instance.id)

    with pytest.raises(DomainValidationError):
        await svc.create(
            source_type.slug,
            EntityInstanceCreate(values={"ref_field": str(target.instance.id)}),
        )


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_returns_instance_with_values(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(db_session, et.id, name="field_a")

    service = _service(db_session, org.id)
    created = await service.create(et.slug, EntityInstanceCreate(values={"field_a": "abc"}))
    fetched = await service.get(et.slug, created.instance.id)

    assert fetched.instance.id == created.instance.id
    assert fetched.values == {"field_a": "abc"}


async def test_get_unknown_id_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    with pytest.raises(NotFoundError):
        await service.get(et.slug, uuid.uuid4())


# ---------------------------------------------------------------------------
# list — org isolation and soft-delete exclusion
# ---------------------------------------------------------------------------


async def test_list_instances_filters_by_org(db_session: AsyncSession) -> None:
    """SPEC-001 §9 — test_list_instances_filters_by_org"""
    org_a = await _make_org(db_session, name="Org A")
    org_b = await _make_org(db_session, name="Org B")
    # Use the same slug for both — possible because they're different orgs
    et_a = await _make_type(db_session, org_a.id, slug="shared-type-a1")
    et_b = await _make_type(db_session, org_b.id, slug="shared-type-b1")

    svc_a = _service(db_session, org_a.id)
    svc_b = _service(db_session, org_b.id)

    await svc_a.create(et_a.slug, EntityInstanceCreate())
    await svc_a.create(et_a.slug, EntityInstanceCreate())
    await svc_b.create(et_b.slug, EntityInstanceCreate())

    items_a, _meta_a = await svc_a.list(et_a.slug, PaginationParams())
    items_b, _meta_b = await svc_b.list(et_b.slug, PaginationParams())

    assert len(items_a) == 2
    assert len(items_b) == 1
    assert all(i.instance.organization_id == org_a.id for i in items_a)
    assert all(i.instance.organization_id == org_b.id for i in items_b)


async def test_soft_deleted_instance_excluded_from_list(db_session: AsyncSession) -> None:
    """SPEC-001 §9 — test_soft_deleted_instance_excluded_from_list"""
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    inst1 = await service.create(et.slug, EntityInstanceCreate())
    inst2 = await service.create(et.slug, EntityInstanceCreate())

    await service.delete(et.slug, inst2.instance.id)

    items, _ = await service.list(et.slug, PaginationParams())
    ids = [i.instance.id for i in items]

    assert inst1.instance.id in ids
    assert inst2.instance.id not in ids


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_applies_partial_values(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(db_session, et.id, name="alpha")
    await _make_attr(db_session, et.id, name="beta")

    service = _service(db_session, org.id)
    created = await service.create(
        et.slug, EntityInstanceCreate(values={"alpha": "a", "beta": "b"})
    )
    updated = await service.update(
        et.slug,
        created.instance.id,
        EntityInstanceUpdate(values={"alpha": "a2"}),
    )
    assert updated.values["alpha"] == "a2"
    assert updated.values["beta"] == "b"  # untouched


async def test_update_writes_audit_log(db_session: AsyncSession) -> None:
    """SPEC-001 §9 — test_update_instance_writes_audit_log"""
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    created = await service.create(et.slug, EntityInstanceCreate())
    await service.update(et.slug, created.instance.id, EntityInstanceUpdate(is_active=False))

    from sqlalchemy import select as sa_select

    result = await db_session.execute(
        sa_select(AuditLog).where(
            AuditLog.resource_type == "EntityInstance",
            AuditLog.resource_id == created.instance.id,
            AuditLog.action == "update",
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_update_missing_required_field_returns_422(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)
    await _make_attr(db_session, et.id, name="must_have", is_required=True)

    service = _service(db_session, org.id)
    created = await service.create(et.slug, EntityInstanceCreate(values={"must_have": "present"}))
    with pytest.raises(DomainValidationError) as exc:
        await service.update(
            et.slug,
            created.instance.id,
            EntityInstanceUpdate(values={"must_have": None}),
        )
    assert "must_have" in exc.value.message


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_soft_deletes_instance(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    created = await service.create(et.slug, EntityInstanceCreate())

    await service.delete(et.slug, created.instance.id)

    assert created.instance.deleted_at is not None


async def test_delete_writes_audit_log(db_session: AsyncSession) -> None:
    """SPEC-001 §9 — test_delete_instance_writes_audit_log"""
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    created = await service.create(et.slug, EntityInstanceCreate())
    await service.delete(et.slug, created.instance.id)

    from sqlalchemy import select as sa_select

    result = await db_session.execute(
        sa_select(AuditLog).where(
            AuditLog.resource_type == "EntityInstance",
            AuditLog.resource_id == created.instance.id,
            AuditLog.action == "delete",
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_delete_unknown_id_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    with pytest.raises(NotFoundError):
        await service.delete(et.slug, uuid.uuid4())


async def test_get_after_delete_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session)
    et = await _make_type(db_session, org.id)

    service = _service(db_session, org.id)
    created = await service.create(et.slug, EntityInstanceCreate())
    await service.delete(et.slug, created.instance.id)

    with pytest.raises(NotFoundError):
        await service.get(et.slug, created.instance.id)
