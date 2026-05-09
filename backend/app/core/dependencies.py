"""Cross-cutting FastAPI dependency factories (ADR-009).

Per-aggregate Service / Repository factories live here for now; if the
import graph forces a split (a future repository imports from another),
each factory will move next to the class it builds.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.security import (
    AuthContext,
    current_org,
    current_person,
    get_auth_context,
    require_permission,
)
from app.repositories.entity_attribute_repository import EntityAttributeRepository
from app.repositories.entity_type_repository import EntityTypeRepository
from app.repositories.organization_repository import OrganizationRepository
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.entity_attribute_service import EntityAttributeService
from app.services.entity_type_service import EntityTypeService
from app.services.organization_service import (
    OrganizationService,
    _OrganizationLifecycle,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Commits on success, rolls back on exception, and always closes the session.
    """
    session_factory = Database.get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_audit_writer(
    request: Request,
    session: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AuditWriter:
    """Construct an ``AuditWriter`` scoped to the current request.

    The writer is bound to the *request* session — its writes commit
    atomically with the business mutation. Failure-path audits are written
    elsewhere, in a fresh session opened by the route-level exception
    handler (ADR-009).
    """
    scope = _AuditScope(
        org_id=auth.organization_id,
        actor_id=auth.person_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return AuditWriter(session, scope)


@lru_cache
def get_organization_lifecycle() -> _OrganizationLifecycle:
    """Singleton ``_OrganizationLifecycle`` instance.

    The cache replaces module-level state (ADR-009). Tests reset by calling
    ``get_organization_lifecycle.cache_clear()`` between cases.
    """
    return _OrganizationLifecycle()


async def get_organization_repository(
    session: AsyncSession = Depends(get_db),
) -> OrganizationRepository:
    """Construct an ``OrganizationRepository`` for the current request."""
    return OrganizationRepository(session)


async def get_organization_service(
    session: AsyncSession = Depends(get_db),
    repo: OrganizationRepository = Depends(get_organization_repository),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
    lifecycle: _OrganizationLifecycle = Depends(get_organization_lifecycle),
) -> OrganizationService:
    """Construct an ``OrganizationService`` with its collaborators wired."""
    return OrganizationService(
        session=session,
        repo=repo,
        audit=audit,
        lifecycle=lifecycle,
        actor_id=auth.person_id,
    )


async def get_entity_type_repository(
    session: AsyncSession = Depends(get_db),
) -> EntityTypeRepository:
    return EntityTypeRepository(session)


async def get_entity_type_service(
    repo: EntityTypeRepository = Depends(get_entity_type_repository),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
) -> EntityTypeService:
    return EntityTypeService(
        repo=repo,
        audit=audit,
        tenant_id=auth.organization_id,
        actor_id=auth.person_id,
    )


async def get_entity_attribute_repository(
    session: AsyncSession = Depends(get_db),
) -> EntityAttributeRepository:
    return EntityAttributeRepository(session)


async def get_entity_attribute_service(
    repo: EntityAttributeRepository = Depends(get_entity_attribute_repository),
    type_repo: EntityTypeRepository = Depends(get_entity_type_repository),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
) -> EntityAttributeService:
    return EntityAttributeService(
        repo=repo,
        type_repo=type_repo,
        audit=audit,
        tenant_id=auth.organization_id,
        actor_id=auth.person_id,
    )


__all__ = [
    "current_org",
    "current_person",
    "get_audit_writer",
    "get_auth_context",
    "get_db",
    "get_entity_attribute_repository",
    "get_entity_attribute_service",
    "get_entity_type_repository",
    "get_entity_type_service",
    "get_organization_lifecycle",
    "get_organization_repository",
    "get_organization_service",
    "require_permission",
]
