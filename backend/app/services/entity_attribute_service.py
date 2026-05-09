"""Service for the EntityAttribute aggregate (ADR-009).

Adds, updates, and removes attributes on an EntityType. Both system and
custom types accept new attributes (SPEC-001 §4); seed attributes on
system types cannot be deleted.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.exceptions import NotFoundError, ResourceLockedError
from app.models.eav import EntityAttribute
from app.repositories.entity_attribute_repository import EntityAttributeRepository
from app.repositories.entity_type_repository import EntityTypeRepository
from app.schemas.eav import EntityAttributeCreate, EntityAttributeUpdate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter


class EntityAttributeService:
    """Use-case orchestrator for the EntityAttribute aggregate."""

    def __init__(
        self,
        repo: EntityAttributeRepository,
        type_repo: EntityTypeRepository,
        audit: AuditWriter,
        tenant_id: UUID,
        actor_id: UUID | None,
    ) -> None:
        self._repo = repo
        self._type_repo = type_repo
        self._audit = audit
        self._tenant_id = tenant_id
        self._actor_id = actor_id

    async def list(
        self, entity_type_id: UUID, params: PaginationParams
    ) -> tuple[Sequence[EntityAttribute], PaginationMeta]:
        """List attributes for an EntityType, paginated."""
        return await self._repo.list_for_type(entity_type_id, params)

    async def get(self, attr_id: UUID, entity_type_id: UUID) -> EntityAttribute:
        """Return an attribute scoped to an EntityType, or raise 404."""
        ea = await self._repo.get_for_type(attr_id, entity_type_id)
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
        await self._repo.save(ea)

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
        await self._repo.save(ea)

        await self._audit.write(
            action="update",
            resource_type="EntityAttribute",
            resource_id=ea.id,
            previous_state=previous,
            next_state=_ea_snapshot(ea),
        )
        return ea

    async def delete(self, attr_id: UUID, entity_type_id: UUID) -> None:
        """Delete an attribute. Attributes on system types are protected."""
        ea = await self.get(attr_id, entity_type_id)

        parent = await self._type_repo.get(entity_type_id)
        if parent is not None and parent.is_system_type:
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
        await self._repo.delete(ea)


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
