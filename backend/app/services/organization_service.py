"""Service for the Organization aggregate.

Class-per-aggregate. Constructor injection of session, audit collaborator,
lifecycle dispatcher, and actor identity. The service orchestrates use cases —
load → mutate via model methods → persist → write success audit via
``AuditWriter``. ``get_db`` owns commit/rollback; this layer never commits.

All SQL for the Organization aggregate lives in the "query helpers" section
at the bottom of the file. ADR-002's explicit-join policy is operationalized
by keeping every query for one aggregate in one auditable file (this one).
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import paginate
from app.models.eav import Organization
from app.schemas.eav import OrganizationCreate, OrganizationUpdate
from app.schemas.pagination import PaginationMeta, PaginationParams
from app.services.audit_service import AuditWriter

_OrganizationCreateListener = Callable[[AsyncSession, UUID], Awaitable[None]]


class _OrganizationLifecycle:
    """Private listener registry for Organization extension points.

    Persisted between calls as a class with private state, not via a
    module-level list. The singleton instance is created by an
    ``lru_cache``d factory in ``core/dependencies.py``; tests override
    that factory or call ``cache_clear()``.
    """

    def __init__(self) -> None:
        self._post_create: list[_OrganizationCreateListener] = []

    def register_post_create(self, fn: _OrganizationCreateListener) -> None:
        """Append ``fn`` to the post-create listener list."""
        self._post_create.append(fn)

    def clear(self) -> None:
        """Remove every registered listener (intended for tests only)."""
        self._post_create.clear()

    async def on_create(self, session: AsyncSession, org_id: UUID) -> None:
        """Invoke every registered post-create listener in registration order.

        Runs inside the same database transaction as the Organization insert
        and audit write. Any exception propagates immediately, rolling back
        the entire transaction via ``get_db``.
        """
        for listener in self._post_create:
            await listener(session, org_id)


class OrganizationService:
    """Use-case orchestrator for the Organization aggregate."""

    def __init__(
        self,
        session: AsyncSession,
        audit: AuditWriter,
        lifecycle: _OrganizationLifecycle,
        actor_id: UUID | None,
    ) -> None:
        self._session = session
        self._audit = audit
        self._lifecycle = lifecycle
        self._actor_id = actor_id

    # ------------------------------------------------------------------
    # Public use-case methods
    # ------------------------------------------------------------------

    async def create(self, data: OrganizationCreate) -> Organization:
        """Create a new Organization tenant.

        Order of writes (same transaction):
          1. Organization INSERT + flush (model factory → ``_save``).
          2. AuditLog INSERT via ``AuditWriter`` (BR-07).
          3. Post-create lifecycle listeners (TASK-029 / TASK-032 hook here).

        Any failure rolls back all three via ``get_db``.
        """
        org = Organization.from_create(data)
        await self._save(org)

        # Organization is the tenant root; the audit row belongs to the
        # just-created org, not the auth context's org (which may be the
        # system actor's stub org or a different tenant).
        await self._audit.write(
            action="create",
            resource_type="Organization",
            resource_id=org.id,
            organization_id=org.id,
            previous_state=None,
            next_state=_org_snapshot(org),
        )

        await self._lifecycle.on_create(self._session, org.id)

        return org

    async def get(self, org_id: UUID) -> Organization:
        """Return an Organization by primary key.

        Raises ``NotFoundError`` if absent — the route-level exception
        handler translates that into a 404 response and writes a failure
        audit.
        """
        org = await self._get_by_id(org_id)
        if org is None:
            raise NotFoundError("Organization", org_id, action="read", actor_id=self._actor_id)
        return org

    async def list(self, params: PaginationParams) -> tuple[Sequence[Organization], PaginationMeta]:
        """Return a cursor-paginated page of organizations."""
        return await self._list_page(params)

    async def update(self, org_id: UUID, data: OrganizationUpdate) -> Organization:
        """Apply a partial update and write an audit entry.

        Only fields explicitly set in the request body are applied
        (``model_dump(exclude_unset=True)`` semantics).
        """
        org = await self.get(org_id)
        previous = _org_snapshot(org)

        updates = data.model_dump(exclude_unset=True)
        address_updates = updates.pop("address", None)
        if address_updates is not None:
            address_field_map = {
                "line1": "address_line1",
                "line2": "address_line2",
                "city": "city",
                "state": "state",
                "postal_code": "postal_code",
                "country": "country",
            }
            for api_key, value in address_updates.items():
                setattr(org, address_field_map[api_key], value)
        for field, value in updates.items():
            setattr(org, field, value)

        org.updated_at = datetime.now(tz=UTC)
        await self._save(org)

        await self._audit.write(
            action="update",
            resource_type="Organization",
            resource_id=org.id,
            organization_id=org.id,
            previous_state=previous,
            next_state=_org_snapshot(org),
        )

        return org

    # ------------------------------------------------------------------
    # Query helpers — every SQL statement for this aggregate lives here.
    # If a query is reused outside this service, that's the signal to
    # extract a Repository class. Until then, inline.
    # ------------------------------------------------------------------

    async def _get_by_id(self, org_id: UUID) -> Organization | None:
        result = await self._session.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def _list_page(
        self, params: PaginationParams
    ) -> tuple[Sequence[Organization], PaginationMeta]:
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

    async def _save(self, org: Organization) -> None:
        self._session.add(org)
        await self._session.flush()


def _org_snapshot(org: Organization) -> dict[str, Any]:
    """Audit-shape snapshot of an Organization.

    Mirrors ``OrganizationResponse`` so the audit trail and API are
    structurally identical.
    """
    return {
        "id": str(org.id),
        "name": org.name,
        "npi_number": org.npi_number,
        "tax_id": org.tax_id,
        "phone": org.phone,
        "address": {
            "line1": org.address_line1,
            "line2": org.address_line2,
            "city": org.city,
            "state": org.state,
            "postal_code": org.postal_code,
            "country": org.country,
        },
        "timezone": org.timezone,
        "is_active": org.is_active,
    }
