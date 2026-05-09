"""Repository for the Organization aggregate (ADR-009).

Owns every query against the ``organizations`` table. The service layer
calls these methods; nothing else touches SQLAlchemy for this aggregate.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.models.eav import Organization
from app.schemas.pagination import PaginationMeta, PaginationParams


class OrganizationRepository:
    """Query owner for the Organization aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, org_id: UUID) -> Organization | None:
        """Return an Organization by primary key, or ``None`` if absent."""
        result = await self._session.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def list_for_page(
        self, params: PaginationParams
    ) -> tuple[Sequence[Organization], PaginationMeta]:
        """Return a cursor-paginated page of organizations.

        The sort-field allowlist is declared inline at use (ADR-009 — no
        module-level mutable state in repositories).
        """
        return await paginate(
            self._session,
            select(Organization),
            params=params,
            sort_fields={
                "created_at": Organization.created_at,
                "updated_at": Organization.updated_at,
                "name": Organization.name,
            },
            id_col=Organization.id,
        )

    async def save(self, org: Organization) -> None:
        """Persist a new or modified Organization.

        Adds the entity to the session and flushes so server defaults and
        identity columns are visible. The ``get_db`` dependency owns the
        commit; this method never commits.
        """
        self._session.add(org)
        await self._session.flush()
