"""Service for the EntityType aggregate.

Manages EntityType lifecycle (create / read / update / delete). System types
are protected from rename and delete via ``EntityType.assert_mutable()``.
Slug uniqueness within an org is checked at the service layer for a friendly
409 envelope; the DB ``UniqueConstraint`` is the safety net.

All SQL for the EntityType aggregate lives in the "query helpers" section
at the bottom of the file (per ADR-002 — explicit joins reviewable in one
place per aggregate).
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, SlugNotFoundError
from app.core.pagination import paginate
from app.models.eav import EntityType
from app.schemas.eav import EntityTypeCreate, EntityTypeUpdate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter


class EntityTypeService:
    """Use-case orchestrator for the EntityType aggregate."""

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

    async def list(self, params: PaginationParams) -> tuple[Sequence[EntityType], PaginationMeta]:
        """Return system types plus the tenant's custom types, paginated."""
        return await self._list_page(params)

    async def get_by_slug(self, slug: str) -> EntityType:
        """Return an EntityType by slug or raise ``SlugNotFoundError``."""
        et = await self._find_by_slug(slug)
        if et is None:
            raise SlugNotFoundError("EntityType", slug)
        return et

    async def create(self, data: EntityTypeCreate) -> EntityType:
        """Create a custom EntityType for the tenant.

        System slugs and intra-org duplicate slugs are rejected with 409.
        Callers gate on ``settings.custom_entity_types_enabled`` at the
        router boundary (see TASK-019 for the auto-permission generation
        that flips the flag on).
        """
        await self._assert_slug_available(data.slug)

        et = EntityType(
            organization_id=self._tenant_id,
            name=data.name,
            slug=data.slug,
            is_system_type=False,
            is_person_subtype=False,
            created_at=datetime.now(tz=UTC),
        )
        await self._save(et)

        await self._audit.write(
            action="create",
            resource_type="EntityType",
            resource_id=et.id,
            next_state=_et_snapshot(et),
        )
        return et

    async def update(self, slug: str, data: EntityTypeUpdate) -> EntityType:
        """Partially update a custom EntityType.

        System types raise 409 via ``assert_mutable``. Slug renames are
        validated for uniqueness; the slug-change permission cascade
        (TASK-019) is owned by a different task.
        """
        et = await self.get_by_slug(slug)
        et.assert_mutable(action="rename")

        previous = _et_snapshot(et)
        updates = data.model_dump(exclude_unset=True)

        new_slug = updates.get("slug")
        if new_slug is not None and new_slug != et.slug:
            await self._assert_slug_available(new_slug, exclude_id=et.id)

        for field, value in updates.items():
            setattr(et, field, value)

        et.updated_at = datetime.now(tz=UTC)
        await self._save(et)

        await self._audit.write(
            action="update",
            resource_type="EntityType",
            resource_id=et.id,
            previous_state=previous,
            next_state=_et_snapshot(et),
        )
        return et

    async def delete(self, slug: str) -> None:
        """Delete a custom EntityType (system types raise 409)."""
        et = await self.get_by_slug(slug)
        et.assert_mutable(action="delete")

        await self._audit.write(
            action="delete",
            resource_type="EntityType",
            resource_id=et.id,
            previous_state=_et_snapshot(et),
        )
        await self._delete(et)

    async def _assert_slug_available(
        self,
        slug: str,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        """Reject system-reserved slugs and intra-org duplicates with 409."""
        if slug in EntityType.SYSTEM_SLUGS:
            raise ConflictError(
                f"Slug '{slug}' is a system-reserved slug and cannot be used for a custom type.",
                details=[{"slug": slug}],
            )
        existing = await self._find_in_scope(slug, self._tenant_id, exclude_id=exclude_id)
        if existing is not None:
            raise ConflictError(
                f"An EntityType with slug '{slug}' already exists in this organization.",
                details=[{"slug": slug}],
            )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def _find_by_slug(self, slug: str) -> EntityType | None:
        result = await self._session.execute(select(EntityType).where(EntityType.slug == slug))
        return result.scalar_one_or_none()

    async def _find_in_scope(
        self,
        slug: str,
        org_id: UUID | None,
        *,
        exclude_id: UUID | None = None,
    ) -> EntityType | None:
        stmt = select(EntityType).where(EntityType.slug == slug)
        if org_id is None:
            stmt = stmt.where(EntityType.organization_id.is_(None))
        else:
            stmt = stmt.where(EntityType.organization_id == org_id)
        if exclude_id is not None:
            stmt = stmt.where(EntityType.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _list_page(
        self, params: PaginationParams
    ) -> tuple[Sequence[EntityType], PaginationMeta]:
        stmt = select(EntityType)
        if self._tenant_id is not None:
            stmt = stmt.where(
                or_(
                    EntityType.organization_id.is_(None),
                    EntityType.organization_id == self._tenant_id,
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

    async def _save(self, et: EntityType) -> None:
        self._session.add(et)
        await self._session.flush()

    async def _delete(self, et: EntityType) -> None:
        await self._session.delete(et)
        await self._session.flush()


def _et_snapshot(et: EntityType) -> dict[str, Any]:
    """Audit-shape snapshot of an EntityType."""
    return {
        "id": str(et.id),
        "organization_id": str(et.organization_id) if et.organization_id else None,
        "name": et.name,
        "slug": et.slug,
        "is_system_type": et.is_system_type,
        "is_person_subtype": et.is_person_subtype,
    }
