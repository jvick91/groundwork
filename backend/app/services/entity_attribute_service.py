"""Service for the EntityAttribute aggregate.

Adds, updates, and removes attributes on an EntityType. Both system and
custom types accept new attributes (SPEC-001 §4); seed attributes on
system types cannot be deleted.

The service expects the parent ``EntityType`` to be passed in by the router
(it has already been fetched via ``EntityTypeService.get_by_slug``); this
avoids duplicating the type lookup inside this aggregate's queries.

All SQL for the EntityAttribute aggregate lives in the "query helpers"
section at the bottom of the file.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ResourceLockedError
from app.core.pagination import paginate
from app.models.eav import EntityAttribute, EntityType
from app.schemas.eav import EntityAttributeCreate, EntityAttributeUpdate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter


class EntityAttributeService:
    """Use-case orchestrator for the EntityAttribute aggregate."""

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
        self, entity_type_id: UUID, params: PaginationParams
    ) -> tuple[Sequence[EntityAttribute], PaginationMeta]:
        """List attributes for an EntityType, paginated."""
        return await self._list_page(entity_type_id, params)

    async def get(self, attr_id: UUID, entity_type_id: UUID) -> EntityAttribute:
        """Return an attribute scoped to an EntityType, or raise 404."""
        ea = await self._find_in_type(attr_id, entity_type_id)
        if ea is None:
            raise NotFoundError(
                "EntityAttribute",
                attr_id,
                action="read",
                actor_id=self._actor_id,
            )
        return ea

    async def create(
        self,
        entity_type_id: UUID,
        data: EntityAttributeCreate,
    ) -> EntityAttribute:
        """Add an attribute to an EntityType (system types are extensible)."""
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
        await self._save(ea)

        await self._audit.write(
            action="create",
            resource_type="EntityAttribute",
            resource_id=ea.id,
            next_state=_ea_snapshot(ea),
        )
        return ea

    async def update(
        self,
        attr_id: UUID,
        entity_type_id: UUID,
        data: EntityAttributeUpdate,
    ) -> EntityAttribute:
        """Partially update an attribute."""
        ea = await self.get(attr_id, entity_type_id)
        previous = _ea_snapshot(ea)

        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(ea, field, value)

        ea.updated_at = datetime.now(tz=UTC)
        await self._save(ea)

        await self._audit.write(
            action="update",
            resource_type="EntityAttribute",
            resource_id=ea.id,
            previous_state=previous,
            next_state=_ea_snapshot(ea),
        )
        return ea

    async def delete(self, attr_id: UUID, parent: EntityType) -> None:
        """Delete an attribute. Attributes on system types are protected.

        ``parent`` is the resolved EntityType (passed in by the router after
        its own ``EntityTypeService.get_by_slug`` call) so this service
        never re-queries for the type.
        """
        ea = await self.get(attr_id, parent.id)

        if parent.is_system_type:
            raise ResourceLockedError(
                "EntityAttribute",
                "attributes on system types cannot be deleted",
            )

        await self._audit.write(
            action="delete",
            resource_type="EntityAttribute",
            resource_id=ea.id,
            previous_state=_ea_snapshot(ea),
        )
        await self._delete(ea)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def _find_in_type(self, attr_id: UUID, entity_type_id: UUID) -> EntityAttribute | None:
        """Return the attribute *if* it belongs to ``entity_type_id``.

        The combined filter prevents cross-type data exposure.
        """
        result = await self._session.execute(
            select(EntityAttribute).where(
                EntityAttribute.id == attr_id,
                EntityAttribute.entity_type_id == entity_type_id,
            )
        )
        return result.scalar_one_or_none()

    async def _list_page(
        self, entity_type_id: UUID, params: PaginationParams
    ) -> tuple[Sequence[EntityAttribute], PaginationMeta]:
        stmt = select(EntityAttribute).where(EntityAttribute.entity_type_id == entity_type_id)
        return await paginate(
            self._session,
            stmt,
            params=params,
            sort_fields={
                "created_at": EntityAttribute.created_at,
                "display_order": EntityAttribute.display_order,
                "name": EntityAttribute.name,
            },
            id_col=EntityAttribute.id,
        )

    async def _save(self, ea: EntityAttribute) -> None:
        self._session.add(ea)
        await self._session.flush()

    async def _delete(self, ea: EntityAttribute) -> None:
        await self._session.delete(ea)
        await self._session.flush()


def _ea_snapshot(ea: EntityAttribute) -> dict[str, Any]:
    """Audit-shape snapshot of an EntityAttribute."""
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
