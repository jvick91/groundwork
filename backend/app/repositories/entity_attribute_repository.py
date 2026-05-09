"""Repository for the EntityAttribute aggregate (ADR-009)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.models.eav import EntityAttribute
from app.schemas.pagination import PaginationMeta, PaginationParams


class EntityAttributeRepository:
    """Query owner for the EntityAttribute aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_type(
        self,
        attr_id: UUID,
        entity_type_id: UUID,
    ) -> EntityAttribute | None:
        """Return an EntityAttribute by ID *if* it belongs to ``entity_type_id``.

        The combined filter prevents cross-type data exposure: an attr_id
        that exists but is scoped to a different EntityType returns ``None``.
        """
        result = await self._session.execute(
            select(EntityAttribute).where(
                EntityAttribute.id == attr_id,
                EntityAttribute.entity_type_id == entity_type_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_type(
        self,
        entity_type_id: UUID,
        params: PaginationParams,
    ) -> tuple[Sequence[EntityAttribute], PaginationMeta]:
        """List attributes for a single EntityType, paginated."""
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

    async def save(self, ea: EntityAttribute) -> None:
        """Persist a new or modified EntityAttribute."""
        self._session.add(ea)
        await self._session.flush()

    async def delete(self, ea: EntityAttribute) -> None:
        """Remove an EntityAttribute (caller must check protection)."""
        await self._session.delete(ea)
        await self._session.flush()
