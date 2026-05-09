"""Repository for the EntityType aggregate (ADR-009).

Owns every query against the ``entity_types`` table. The service layer
calls these methods; nothing else touches SQLAlchemy for this aggregate.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.models.eav import EntityType
from app.schemas.pagination import PaginationMeta, PaginationParams


class EntityTypeRepository:
    """Query owner for the EntityType aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, entity_type_id: UUID) -> EntityType | None:
        """Return an EntityType by primary key, or ``None`` if absent."""
        result = await self._session.execute(
            select(EntityType).where(EntityType.id == entity_type_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> EntityType | None:
        """Return an EntityType by slug, or ``None`` if absent."""
        result = await self._session.execute(select(EntityType).where(EntityType.slug == slug))
        return result.scalar_one_or_none()

    async def find_in_scope(
        self,
        slug: str,
        org_id: UUID | None,
        *,
        exclude_id: UUID | None = None,
    ) -> EntityType | None:
        """Return an EntityType matching ``slug`` within the given scope.

        ``org_id is None`` is the system-scope match (``organization_id IS NULL``).
        ``exclude_id`` filters out a known row when checking for duplicates
        during an update.
        """
        stmt = select(EntityType).where(EntityType.slug == slug)
        if org_id is None:
            stmt = stmt.where(EntityType.organization_id.is_(None))
        else:
            stmt = stmt.where(EntityType.organization_id == org_id)
        if exclude_id is not None:
            stmt = stmt.where(EntityType.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_page(
        self,
        params: PaginationParams,
        *,
        org_id: UUID | None,
    ) -> tuple[Sequence[EntityType], PaginationMeta]:
        """List system types plus the given org's custom types, paginated."""
        stmt = select(EntityType)
        if org_id is not None:
            stmt = stmt.where(
                or_(
                    EntityType.organization_id.is_(None),
                    EntityType.organization_id == org_id,
                )
            )
        return await paginate(
            self._session,
            stmt,
            params=params,
            sort_fields={
                "created_at": EntityType.created_at,
                "name": EntityType.name,
                "slug": EntityType.slug,
            },
            id_col=EntityType.id,
        )

    async def save(self, et: EntityType) -> None:
        """Persist a new or modified EntityType."""
        self._session.add(et)
        await self._session.flush()

    async def delete(self, et: EntityType) -> None:
        """Remove an EntityType (caller must check ``is_system_type``)."""
        await self._session.delete(et)
        await self._session.flush()
