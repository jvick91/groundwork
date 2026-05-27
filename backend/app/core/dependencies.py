"""Cross-cutting FastAPI dependency factories.

Per-aggregate Service factories live here. Each Service takes its session
directly (no Repository class — all SQL for the aggregate lives inside the
Service file under a ``# Query helpers`` section). If queries for an
aggregate ever become shared across multiple services, that is the signal
to extract a Repository class.
"""

from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.core.config import settings
from app.core.database import Database, get_db
from app.core.security import (
    AuthContext,
    current_org,
    current_person,
    get_auth_context,
    require_permission,
    require_type_permission,
)
from app.services.audit_service import AuditWriter, _AuditScope
from app.services.auth0_management_service import Auth0ManagementService
from app.services.auth0_sync_service import Auth0SyncService
from app.services.entity_attribute_service import EntityAttributeService
from app.services.entity_instance_service import EntityInstanceService
from app.services.entity_type_service import EntityTypeService
from app.services.identity_service import PersonService
from app.services.organization_service import (
    OrganizationService,
    _OrganizationLifecycle,
)


async def get_audit_writer(
    request: Request,
    session: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AuditWriter:
    """Construct an ``AuditWriter`` scoped to the current request.

    The writer is bound to the *request* session — its writes commit
    atomically with the business mutation. Failure-path audits are written
    elsewhere, in a fresh session opened by the route-level exception
    handler.
    """
    scope = _AuditScope(
        org_id=auth.organization_id,
        actor_id=auth.person_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return AuditWriter(session, scope)


@lru_cache
def get_auth0_management_service() -> Auth0ManagementService | None:
    """Singleton Auth0ManagementService.

    Returns ``None`` when management credentials are not configured (local dev
    with stub auth). Callers must handle ``None`` gracefully — the sync service
    wraps this check.
    """
    if not settings.auth0_management_client_id or not settings.auth0_management_client_secret:
        return None
    client = httpx.AsyncClient(timeout=15.0)
    return Auth0ManagementService(client)


def get_auth0_sync_service(
    management: Auth0ManagementService | None = Depends(get_auth0_management_service),
) -> Auth0SyncService | None:
    """Return an Auth0SyncService when credentials are configured, else None."""
    if management is None:
        return None
    return Auth0SyncService(management)


@lru_cache
def get_organization_lifecycle() -> _OrganizationLifecycle:
    """Singleton ``_OrganizationLifecycle`` instance.

    The cache replaces module-level state. Tests reset by calling
    ``get_organization_lifecycle.cache_clear()`` between cases.
    """
    return _OrganizationLifecycle()


async def get_organization_service(
    session: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
    lifecycle: _OrganizationLifecycle = Depends(get_organization_lifecycle),
) -> OrganizationService:
    """Construct an ``OrganizationService`` with its collaborators wired."""
    return OrganizationService(
        session=session,
        audit=audit,
        lifecycle=lifecycle,
        actor_id=auth.person_id,
    )


async def get_entity_type_service(
    session: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
) -> EntityTypeService:
    return EntityTypeService(
        session=session,
        audit=audit,
        tenant_id=auth.organization_id,
        actor_id=auth.person_id,
    )


async def get_entity_attribute_service(
    session: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
) -> EntityAttributeService:
    return EntityAttributeService(
        session=session,
        audit=audit,
        tenant_id=auth.organization_id,
        actor_id=auth.person_id,
    )


async def get_entity_instance_service(
    session: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
) -> EntityInstanceService:
    return EntityInstanceService(
        session=session,
        audit=audit,
        tenant_id=auth.organization_id,
        actor_id=auth.person_id,
    )


async def get_person_service(
    session: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    auth: AuthContext = Depends(get_auth_context),
    auth0_sync: Auth0SyncService | None = Depends(get_auth0_sync_service),
) -> PersonService:
    return PersonService(
        session=session,
        audit=audit,
        tenant_id=auth.organization_id,
        actor_id=auth.person_id,
        auth0_sync=auth0_sync,
    )


__all__ = [
    "current_org",
    "current_person",
    "get_audit_writer",
    "get_auth0_management_service",
    "get_auth0_sync_service",
    "get_auth_context",
    "get_db",
    "get_entity_attribute_service",
    "get_entity_instance_service",
    "get_entity_type_service",
    "get_organization_lifecycle",
    "get_organization_service",
    "get_person_service",
    "require_permission",
    "require_type_permission",
]
