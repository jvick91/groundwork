"""Service for the EntityType aggregate (ADR-009).

Manages EntityType lifecycle (create / read / update / delete). System types
are protected from rename and delete via ``EntityType.assert_mutable()``.
Slug uniqueness within an org is checked at the service layer for a friendly
409 envelope; the DB ``UniqueConstraint`` is the safety net.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.exceptions import ConflictError, SlugNotFoundError
from app.models.eav import EntityType
from app.repositories.entity_type_repository import EntityTypeRepository
from app.schemas.eav import EntityTypeCreate, EntityTypeUpdate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter


class EntityTypeService:
    """Use-case orchestrator for the EntityType aggregate."""

    def __init__(
        self,
        repo: EntityTypeRepository,
        audit: AuditWriter,
        tenant_id: UUID,
        actor_id: UUID | None,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._tenant_id = tenant_id
        self._actor_id = actor_id

    async def list(self, params: PaginationParams) -> tuple[Sequence[EntityType], PaginationMeta]:
        """Return system types plus the tenant's custom types, paginated."""
        return await self._repo.list_for_page(params, org_id=self._tenant_id)

    async def get_by_slug(self, slug: str) -> EntityType:
        """Return an EntityType by slug or raise ``SlugNotFoundError``."""
        et = await self._repo.get_by_slug(slug)
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
        await self._repo.save(et)

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
        await self._repo.save(et)

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
        await self._repo.delete(et)

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
        existing = await self._repo.find_in_scope(slug, self._tenant_id, exclude_id=exclude_id)
        if existing is not None:
            raise ConflictError(
                f"An EntityType with slug '{slug}' already exists in this organization.",
                details=[{"slug": slug}],
            )


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
