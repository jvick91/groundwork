"""
Integration tests for app.services.eav_queries (TASK-011B acceptance criteria).

Covers:
  - Correct attribute key-value pairs in aggregated JSONB for a multi-attribute instance
  - Instance with no attribute values returns empty attributes dict
  - Soft-deleted instances excluded from results
  - Multi-tenant isolation (only instances from org_id are returned)
  - Cursor pagination: second page, next_cursor, previous_cursor
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.eav import FieldType
from app.models.eav import (
    AttributeValue,
    EntityAttribute,
    EntityInstance,
    EntityType,
    Organization,
)
from app.schemas.pagination import PaginationParams
from app.services.eav_queries import list_instances_jsonb

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Local fixture helpers (mirrors test_entity_instance_service.py patterns)
# ---------------------------------------------------------------------------


async def _make_org(session: AsyncSession, *, name: str = "Queries Test Org") -> Organization:
    org = Organization(id=uuid.uuid4(), name=name, timezone="UTC", is_active=True)
    session.add(org)
    await session.flush()
    return org


async def _make_type(
    session: AsyncSession,
    org_id: uuid.UUID | None = None,
    *,
    slug: str | None = None,
) -> EntityType:
    et = EntityType(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Queries Test Type",
        slug=slug or f"qt-{uuid.uuid4().hex[:6]}",
        is_system_type=False,
        is_person_subtype=False,
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
    options: Any = None,
) -> EntityAttribute:
    ea = EntityAttribute(
        id=uuid.uuid4(),
        entity_type_id=entity_type_id,
        name=name,
        display_name=name,
        field_type=field_type,
        is_required=False,
        options=options,
        display_order=0,
    )
    session.add(ea)
    await session.flush()
    return ea


async def _make_instance(
    session: AsyncSession,
    org_id: uuid.UUID,
    entity_type_id: uuid.UUID,
    *,
    is_active: bool = True,
    deleted: bool = False,
    created_at: datetime | None = None,
) -> EntityInstance:
    now = created_at or datetime.now(tz=UTC)
    inst = EntityInstance(
        id=uuid.uuid4(),
        organization_id=org_id,
        entity_type_id=entity_type_id,
        is_active=is_active,
        created_at=now,
        deleted_at=now if deleted else None,
    )
    session.add(inst)
    await session.flush()
    return inst


async def _add_value(
    session: AsyncSession,
    instance_id: uuid.UUID,
    attr_id: uuid.UUID,
    value: str | None,
) -> AttributeValue:
    av = AttributeValue(
        id=uuid.uuid4(),
        entity_instance_id=instance_id,
        entity_attribute_id=attr_id,
        value=value,
    )
    session.add(av)
    await session.flush()
    return av


def _params(**kwargs: Any) -> PaginationParams:
    defaults: dict[str, Any] = {
        "limit": 20, "cursor": None, "sort": "created_at", "sort_dir": "desc",
    }
    defaults.update(kwargs)
    return PaginationParams(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAggregationCorrectness:
    async def test_multi_attribute_instance_returns_correct_values(
        self, db_session: AsyncSession
    ) -> None:
        """AC: aggregation returns correct attribute key-value pairs for a multi-attribute instance."""  # noqa: E501
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)
        attr_a = await _make_attr(db_session, et.id, name="field_a")
        attr_b = await _make_attr(db_session, et.id, name="field_b")

        inst = await _make_instance(db_session, org.id, et.id)
        await _add_value(db_session, inst.id, attr_a.id, "hello")
        await _add_value(db_session, inst.id, attr_b.id, "world")
        await db_session.commit()

        rows, _meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert len(rows) == 1
        returned_inst, attrs = rows[0]
        assert returned_inst.id == inst.id
        assert attrs == {"field_a": "hello", "field_b": "world"}

    async def test_instance_with_no_values_returns_empty_dict(
        self, db_session: AsyncSession
    ) -> None:
        """AC: instance with no attribute values returns empty attributes dict."""
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)
        # Define an attribute but add NO values for this instance.
        await _make_attr(db_session, et.id, name="unused_field")

        await _make_instance(db_session, org.id, et.id)
        await db_session.commit()

        rows, _ = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert len(rows) == 1
        _, attrs = rows[0]
        assert attrs == {}

    async def test_null_value_appears_in_attributes(
        self, db_session: AsyncSession
    ) -> None:
        """A value row with NULL value should appear as None in the attributes dict."""
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)
        attr = await _make_attr(db_session, et.id, name="nullable_field")

        inst = await _make_instance(db_session, org.id, et.id)
        await _add_value(db_session, inst.id, attr.id, None)
        await db_session.commit()

        rows, _ = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert len(rows) == 1
        _, attrs = rows[0]
        # jsonb_object_agg includes NULL values; the key exists with None.
        assert "nullable_field" in attrs
        assert attrs["nullable_field"] is None


class TestSoftDeleteExclusion:
    async def test_soft_deleted_instances_excluded(
        self, db_session: AsyncSession
    ) -> None:
        """AC: soft-deleted instances are excluded from results."""
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)

        alive = await _make_instance(db_session, org.id, et.id)
        await _make_instance(db_session, org.id, et.id, deleted=True)
        await db_session.commit()

        rows, _meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert len(rows) == 1
        assert rows[0][0].id == alive.id

    async def test_all_deleted_returns_empty(
        self, db_session: AsyncSession
    ) -> None:
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)

        await _make_instance(db_session, org.id, et.id, deleted=True)
        await db_session.commit()

        rows, meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert rows == []
        assert meta.has_next is False


class TestMultiTenantIsolation:
    async def test_org_filter_excludes_other_tenant(
        self, db_session: AsyncSession
    ) -> None:
        org_a = await _make_org(db_session, name="Org A")
        org_b = await _make_org(db_session, name="Org B")
        et = await _make_type(db_session, org_a.id)

        inst_a = await _make_instance(db_session, org_a.id, et.id)
        # Instance belonging to org_b but same type (simulates cross-tenant pollution).
        await _make_instance(db_session, org_b.id, et.id)
        await db_session.commit()

        rows, _ = await list_instances_jsonb(
            db_session,
            org_id=org_a.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert len(rows) == 1
        assert rows[0][0].id == inst_a.id

    async def test_entity_type_filter(
        self, db_session: AsyncSession
    ) -> None:
        """Instances of a different entity type in the same org are excluded."""
        org = await _make_org(db_session)
        et_a = await _make_type(db_session, org.id, slug=f"type-a-{uuid.uuid4().hex[:4]}")
        et_b = await _make_type(db_session, org.id, slug=f"type-b-{uuid.uuid4().hex[:4]}")

        inst_a = await _make_instance(db_session, org.id, et_a.id)
        await _make_instance(db_session, org.id, et_b.id)
        await db_session.commit()

        rows, _ = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et_a.id,
            params=_params(),
        )

        assert len(rows) == 1
        assert rows[0][0].id == inst_a.id


class TestPagination:
    async def test_limit_respected(self, db_session: AsyncSession) -> None:
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)

        for _ in range(5):
            await _make_instance(db_session, org.id, et.id)
        await db_session.commit()

        rows, meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(limit=3),
        )

        assert len(rows) == 3
        assert meta.has_next is True
        assert meta.next_cursor is not None

    async def test_second_page_excludes_first_page_items(
        self, db_session: AsyncSession
    ) -> None:
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)

        for _ in range(4):
            await _make_instance(db_session, org.id, et.id)
        await db_session.commit()

        first_rows, first_meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(limit=2),
        )
        assert len(first_rows) == 2
        assert first_meta.has_next is True

        second_rows, second_meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(limit=2, cursor=first_meta.next_cursor),
        )
        assert len(second_rows) == 2
        assert second_meta.has_next is False

        first_ids = {r[0].id for r in first_rows}
        second_ids = {r[0].id for r in second_rows}
        assert first_ids.isdisjoint(second_ids), "Pages must not overlap"

    async def test_empty_result_meta_flags(self, db_session: AsyncSession) -> None:
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)
        await db_session.commit()

        rows, meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert rows == []
        assert meta.has_next is False
        assert meta.has_previous is False
        assert meta.next_cursor is None

    async def test_previous_cursor_set_on_page_two(self, db_session: AsyncSession) -> None:
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)

        for _ in range(3):
            await _make_instance(db_session, org.id, et.id)
        await db_session.commit()

        _first_rows, first_meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(limit=2),
        )

        _, second_meta = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(limit=2, cursor=first_meta.next_cursor),
        )

        assert second_meta.has_previous is True
        assert second_meta.previous_cursor is not None


class TestReturnShape:
    async def test_instance_fields_are_populated(self, db_session: AsyncSession) -> None:
        """The EntityInstance object returned from the aggregation has expected fields."""
        org = await _make_org(db_session)
        et = await _make_type(db_session, org.id)
        inst = await _make_instance(db_session, org.id, et.id)
        await db_session.commit()

        rows, _ = await list_instances_jsonb(
            db_session,
            org_id=org.id,
            entity_type_id=et.id,
            params=_params(),
        )

        assert len(rows) == 1
        returned_inst, _ = rows[0]
        assert returned_inst.id == inst.id
        assert returned_inst.organization_id == org.id
        assert returned_inst.entity_type_id == et.id
        assert returned_inst.is_active is True
        assert returned_inst.deleted_at is None
