"""
Authentication and authorization primitives.

Phase 2 (Identity/RBAC - SPEC-002) will replace the stub get_auth_context
with real Auth0 JWT validation via auth0-fastapi-api.
"""

from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.params import Depends as DependsParam


@dataclass
class AuthContext:
    """Authenticated user context extracted from a validated JWT."""

    person_id: UUID
    auth_subject: str
    organization_id: UUID
    role_slugs: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)


async def get_auth_context() -> AuthContext:
    """Extract and validate auth context from the incoming request.

    TODO: Phase 2 - Replace with Auth0 JWT validation.
    """
    raise HTTPException(
        status_code=501,
        detail="Authentication not implemented. See Phase 2 (SPEC-002).",
    )


def require_permission(permission_slug: str) -> DependsParam:
    """Dependency factory that checks whether the authenticated user has a specific permission.

    Usage:
        @router.get("/resource", dependencies=[Depends(require_permission("resource:read"))])
    """

    async def _check_permission(
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if permission_slug not in auth.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: {permission_slug}",
            )
        return auth

    return cast(DependsParam, Depends(_check_permission))
