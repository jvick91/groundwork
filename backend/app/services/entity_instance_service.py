"""Service for the EntityInstance + AttributeValue aggregate (SPEC-001 §4, §6).

Implements the full CRUD surface for EntityInstances and their associated
AttributeValues:

- list: paginated instances of a type, soft-deleted rows excluded
- get: single instance with all values, org-scoped
- create: persist instance + validate/upsert values, enforce required fields
- update: partial update of instance fields and/or values
- delete: soft-delete (sets deleted_at)

Type-casting for every AttributeValue is delegated to
``app.services.eav_type_casting.cast_attribute_value``. This service wires
in the ``validate_fk_existence`` hook that checks the referenced
EntityInstance exists, is not soft-deleted, belongs to the same org, and
matches the EntityType slug stored in ``EntityAttribute.options``.

All SQL lives in the ``# Query helpers`` section at the bottom of this file
(ADR-002 / ADR-009 amendment).

Audit rules (SPEC-001 §7):
- EntityInstance create/update/delete: full instance snapshot (no values).
- AttributeValue changes: snapshot contains ONLY entity_attribute_id and
  entity_instance_id — the ``value`` field is NEVER written to the audit log
  (``filter_phi`` covers this because ``"value"`` is in PHI_EXCLUDED_FIELDS).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.enums.eav import FieldType
from app.models.eav import AttributeValue, EntityAttribute, EntityInstance, EntityType
from app.models.identity import Person
from app.schemas.eav import EntityInstanceCreate, EntityInstanceUpdate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter
from app.services.eav_queries import list_instances_jsonb
from app.services.eav_type_casting import cast_attribute_value


@dataclass
class EntityInstanceWithValues:
    """Paired result from service methods that return an instance and its values."""

    instance: EntityInstance
    values: dict[str, str | None]


class EntityInstanceService:
    """Use-case orchestrator for the EntityInstance + AttributeValue aggregate."""

    def __init__(
        self,
        session: AsyncSession,
        audit: AuditWriter,
        tenant_id: UUID,
        actor_id: UUID | None,
    ) -> None:
        self._session = session
        self._audit = audit
        self._tenant_id = tenant_id
        self._actor_id = actor_id

    # ------------------------------------------------------------------
    # Public use-case methods
    # ------------------------------------------------------------------

    async def list(
        self, type_slug: str, params: PaginationParams
    ) -> tuple[list[EntityInstanceWithValues], PaginationMeta]:
        """Return paginated non-deleted instances using the JSONB aggregation query.

        Delegates to ``list_instances_jsonb`` (ADR-004) which collapses the
        three-table join into a single query, returning one row per instance
        with all attribute values as a JSONB object.
        """
        et = await self._get_entity_type(type_slug)
        rows, meta = await list_instances_jsonb(
            self._session,
            org_id=self._tenant_id,
            entity_type_id=et.id,
            params=params,
        )
        result = [
            EntityInstanceWithValues(instance=inst, values=values)
            for inst, values in rows
        ]
        return result, meta

    async def get(self, type_slug: str, instance_id: UUID) -> EntityInstanceWithValues:
        """Return a single non-deleted instance scoped to the tenant, or raise 404."""
        et = await self._get_entity_type(type_slug)
        inst = await self._find_instance(instance_id, et.id)
        if inst is None:
            raise NotFoundError(
                "EntityInstance",
                instance_id,
                action="read",
                actor_id=self._actor_id,
            )
        values = await self._load_values(instance_id)
        return EntityInstanceWithValues(instance=inst, values=values)

    async def create(
        self, type_slug: str, data: EntityInstanceCreate
    ) -> EntityInstanceWithValues:
        """Create a new EntityInstance and persist its initial AttributeValues.

        Validates every value against its EntityAttribute's field_type (including
        FK existence checks). Enforces required fields after values are written.
        Writes audit entries for the instance and each value change.
        """
        et = await self._get_entity_type(type_slug)

        if data.person_id is not None:
            await self._validate_person_id(data.person_id)

        now = datetime.now(tz=UTC)

        inst = EntityInstance(
            entity_type_id=et.id,
            organization_id=self._tenant_id,
            person_id=data.person_id,
            is_active=True,
            created_at=now,
        )
        await self._save(inst)

        # Validate and persist all submitted values
        attrs = await self._load_attributes(et.id)
        attr_by_name = {a.name: a for a in attrs}

        for attr_name, raw_value in data.values.items():
            attr = attr_by_name.get(attr_name)
            if attr is None:
                raise DomainValidationError(
                    message=f"{attr_name}: unknown attribute for type '{type_slug}'",
                    details=[{"attribute": attr_name, "reason": "unknown attribute"}],
                )
            canonical = await self._cast(attr_name, attr.field_type, raw_value, attr.options)
            await self._upsert_value(inst.id, attr.id, canonical, is_create=True)

        await self._enforce_required(inst.id, attrs)

        await self._audit.write(
            action="create",
            resource_type="EntityInstance",
            resource_id=inst.id,
            next_state=_instance_snapshot(inst),
        )

        values = await self._load_values(inst.id)
        return EntityInstanceWithValues(instance=inst, values=values)

    async def update(
        self, type_slug: str, instance_id: UUID, data: EntityInstanceUpdate
    ) -> EntityInstanceWithValues:
        """Partial update of an EntityInstance (PATCH semantics).

        Only fields explicitly present in ``data`` are applied to the instance.
        ``data.values`` is a merge dict — only supplied attribute keys are updated.
        Required-field enforcement runs after all changes are applied.
        """
        et = await self._get_entity_type(type_slug)
        inst = await self._find_instance(instance_id, et.id)
        if inst is None:
            raise NotFoundError(
                "EntityInstance",
                instance_id,
                action="update",
                actor_id=self._actor_id,
            )

        previous = _instance_snapshot(inst)

        if data.is_active is not None:
            inst.is_active = data.is_active
        if data.person_id is not None:
            await self._validate_person_id(data.person_id)
            inst.person_id = data.person_id

        inst.updated_at = datetime.now(tz=UTC)
        await self._save(inst)

        if data.values is not None:
            attrs = await self._load_attributes(et.id)
            attr_by_name = {a.name: a for a in attrs}

            for attr_name, raw_value in data.values.items():
                attr = attr_by_name.get(attr_name)
                if attr is None:
                    raise DomainValidationError(
                        message=f"{attr_name}: unknown attribute for type '{type_slug}'",
                        details=[{"attribute": attr_name, "reason": "unknown attribute"}],
                    )
                canonical = await self._cast(attr_name, attr.field_type, raw_value, attr.options)
                await self._upsert_value(inst.id, attr.id, canonical, is_create=False)

            await self._enforce_required(inst.id, attrs)

        await self._audit.write(
            action="update",
            resource_type="EntityInstance",
            resource_id=inst.id,
            previous_state=previous,
            next_state=_instance_snapshot(inst),
        )

        values = await self._load_values(inst.id)
        return EntityInstanceWithValues(instance=inst, values=values)

    async def delete(self, type_slug: str, instance_id: UUID) -> None:
        """Soft-delete an EntityInstance (sets deleted_at, BR-05)."""
        et = await self._get_entity_type(type_slug)
        inst = await self._find_instance(instance_id, et.id)
        if inst is None:
            raise NotFoundError(
                "EntityInstance",
                instance_id,
                action="delete",
                actor_id=self._actor_id,
            )

        previous = _instance_snapshot(inst)
        inst.deleted_at = datetime.now(tz=UTC)
        inst.updated_at = inst.deleted_at
        await self._save(inst)

        await self._audit.write(
            action="delete",
            resource_type="EntityInstance",
            resource_id=inst.id,
            previous_state=previous,
            next_state=_instance_snapshot(inst),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _validate_person_id(self, person_id: UUID) -> None:
        """Raise 422 if the person_id does not reference a live Person row.

        Person is tenant-independent, so no org filter is applied here.
        Raises DomainValidationError so the caller receives a 422 instead of
        a raw FK IntegrityError from the database.
        """
        row = await self._session.execute(
            select(Person.id).where(
                Person.id == person_id,
                Person.deleted_at.is_(None),
            )
        )
        if row.scalar_one_or_none() is None:
            raise DomainValidationError(
                message=f"person_id '{person_id}': no active Person with that ID exists",
                details=[{"field": "person_id", "reason": "person not found"}],
            )

    async def _cast(
        self,
        attr_name: str,
        field_type: FieldType,
        value: str | None,
        options: Any,
    ) -> str | None:
        """Validate and canonicalize a value, wiring in the FK existence hook."""
        return await cast_attribute_value(
            attr_name,
            field_type,
            value,
            options,
            validate_fk_existence=self._check_fk_existence if field_type == FieldType.FK else None,
        )

    async def _check_fk_existence(self, value: str, options: str | None) -> None:
        """FK validation hook: existence, not-deleted, same-org, correct type slug.

        ``value`` is the canonicalized UUID string (already v4-validated).
        ``options`` is the target EntityType slug stored on the EntityAttribute.
        Raises ``DomainValidationError`` on any violation.
        """
        fk_id = UUID(value)
        row = await self._session.execute(
            select(EntityInstance.id, EntityType.slug)
            .join(EntityType, EntityType.id == EntityInstance.entity_type_id)
            .where(
                EntityInstance.id == fk_id,
                EntityInstance.organization_id == self._tenant_id,
                EntityInstance.deleted_at.is_(None),
            )
        )
        found = row.one_or_none()

        if found is None:
            raise DomainValidationError(
                message=(
                    f"fk value '{value}': referenced EntityInstance"
                    " does not exist or is not accessible"
                ),
                details=[{"value": value, "reason": "referenced instance not found"}],
            )

        if options is not None and found[1] != options:
            raise DomainValidationError(
                message=f"fk value '{value}': expected entity type '{options}', got '{found[1]}'",
                details=[
                    {
                        "value": value,
                        "expected_type": options,
                        "actual_type": found[1],
                    }
                ],
            )

    async def _enforce_required(
        self, instance_id: UUID, attrs: Sequence[EntityAttribute]
    ) -> None:
        """Raise 422 if any required attribute is missing or null on the instance."""
        required = {a.id: a.name for a in attrs if a.is_required}
        if not required:
            return

        result = await self._session.execute(
            select(AttributeValue.entity_attribute_id, AttributeValue.value).where(
                AttributeValue.entity_instance_id == instance_id,
                AttributeValue.entity_attribute_id.in_(list(required.keys())),
            )
        )
        present = {row[0]: row[1] for row in result.fetchall()}

        missing = [
            required[attr_id]
            for attr_id in required
            if present.get(attr_id) is None
        ]
        if missing:
            raise DomainValidationError(
                message=f"required fields are missing or null: {', '.join(sorted(missing))}",
                details=[
                    {"attribute": name, "reason": "required field is missing or null"}
                    for name in sorted(missing)
                ],
            )

    async def _upsert_value(
        self,
        instance_id: UUID,
        attr_id: UUID,
        canonical: str | None,
        *,
        is_create: bool,
    ) -> None:
        """Write or overwrite an AttributeValue row.

        AttributeValue has no timestamps — changes are tracked via the parent
        EntityInstance's AuditLog rows (SPEC-001 §2 design note). The audit
        entry written here records the attribute and instance IDs but NEVER the
        value itself (``filter_phi`` strips ``"value"``).
        """
        result = await self._session.execute(
            select(AttributeValue).where(
                AttributeValue.entity_instance_id == instance_id,
                AttributeValue.entity_attribute_id == attr_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            av = AttributeValue(
                entity_instance_id=instance_id,
                entity_attribute_id=attr_id,
                value=canonical,
            )
            self._session.add(av)
            await self._session.flush()
            audit_action = "create"
            av_id = av.id
        else:
            existing.value = canonical
            await self._session.flush()
            audit_action = "update"
            av_id = existing.id

        # Snapshot intentionally omits ``value`` (SPEC-001 §7 PHI rule).
        # filter_phi would strip it anyway; we never include it as defence-in-depth.
        snapshot: dict[str, Any] = {
            "entity_attribute_id": str(attr_id),
            "entity_instance_id": str(instance_id),
        }
        if is_create or audit_action == "create":
            await self._audit.write(
                action=audit_action,
                resource_type="AttributeValue",
                resource_id=av_id,
                next_state=snapshot,
            )
        else:
            await self._audit.write(
                action=audit_action,
                resource_type="AttributeValue",
                resource_id=av_id,
                previous_state=snapshot,
                next_state=snapshot,
            )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def _get_entity_type(self, slug: str) -> EntityType:
        """Find an EntityType by slug that belongs to this tenant or is system-scoped."""
        result = await self._session.execute(
            select(EntityType).where(
                EntityType.slug == slug,
                or_(
                    EntityType.organization_id.is_(None),
                    EntityType.organization_id == self._tenant_id,
                ),
            )
        )
        et = result.scalar_one_or_none()
        if et is None:
            from app.core.exceptions import SlugNotFoundError

            raise SlugNotFoundError("EntityType", slug)
        return et

    async def _find_instance(
        self, instance_id: UUID, entity_type_id: UUID
    ) -> EntityInstance | None:
        """Return a non-deleted instance scoped to this tenant and type."""
        result = await self._session.execute(
            select(EntityInstance).where(
                EntityInstance.id == instance_id,
                EntityInstance.organization_id == self._tenant_id,
                EntityInstance.entity_type_id == entity_type_id,
                EntityInstance.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _load_attributes(self, entity_type_id: UUID) -> Sequence[EntityAttribute]:
        result = await self._session.execute(
            select(EntityAttribute).where(EntityAttribute.entity_type_id == entity_type_id)
        )
        return result.scalars().all()

    async def _load_values(self, instance_id: UUID) -> dict[str, str | None]:
        """Load all AttributeValues for one instance, keyed by attribute name."""
        result = await self._session.execute(
            select(EntityAttribute.name, AttributeValue.value)
            .join(EntityAttribute, EntityAttribute.id == AttributeValue.entity_attribute_id)
            .where(AttributeValue.entity_instance_id == instance_id)
        )
        return {row[0]: row[1] for row in result.fetchall()}

    async def _save(self, obj: EntityInstance) -> None:
        self._session.add(obj)
        await self._session.flush()


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _instance_snapshot(inst: EntityInstance) -> dict[str, Any]:
    """Audit-shape snapshot of an EntityInstance (no AttributeValues)."""
    return {
        "id": str(inst.id),
        "entity_type_id": str(inst.entity_type_id),
        "organization_id": str(inst.organization_id),
        "person_id": str(inst.person_id) if inst.person_id else None,
        "is_active": inst.is_active,
        "deleted_at": inst.deleted_at.isoformat() if inst.deleted_at else None,
    }
