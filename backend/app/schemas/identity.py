"""
Pydantic schemas for the Identity domain (SPEC-002 §2).

Person is tenant-independent. Schemas are the HTTP contract; the service
layer maps fields onto the ORM and never returns these `*Response` types
itself (ADR-009 amendment — services don't construct Response schemas).
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums.identity import RoleDomain


class PersonCreate(BaseModel):
    """Create payload for a Person identity record.

    ``auth_subject`` is nullable so non-authenticating personas (clients,
    guardians during MVP per SPEC-002 §4) can be created without an Auth0
    binding.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(..., min_length=1, max_length=255, description="Legal first name.")
    last_name: str = Field(..., min_length=1, max_length=255, description="Legal last name.")
    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Primary email address. Unique across the platform.",
    )
    auth_subject: str | None = Field(
        default=None,
        max_length=255,
        description="Auth0 'sub' claim. Null for clients/guardians (MVP).",
    )
    phone: str | None = Field(
        default=None,
        pattern=r"^[\d\s\-+().]{7,20}$",
        description="Primary phone number.",
    )
    date_of_birth: date | None = Field(
        default=None,
        description="Date of birth. PHI — excluded from audit and logs per BR-08.",
    )


class PersonUpdate(BaseModel):
    """Partial update payload — only fields explicitly set are applied.

    ``email`` and ``auth_subject`` are unique columns; the service surfaces
    duplicates as a 409 ``ConflictError`` before the DB constraint fires.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(
        default=None,
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    auth_subject: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, pattern=r"^[\d\s\-+().]{7,20}$")
    date_of_birth: date | None = None
    is_active: bool | None = None


class PersonResponse(BaseModel):
    """API response shape for a Person record.

    Mirrors the ORM column set including ``deleted_at`` so consumers can
    distinguish live rows from soft-deleted ones in admin contexts.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    auth_subject: str | None
    first_name: str
    last_name: str
    email: str
    phone: str | None
    date_of_birth: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None
    deleted_at: datetime | None


# ---------------------------------------------------------------------------
# RBAC schemas (TASK-013 — no API endpoints yet; used by TASK-014/016/017)
# ---------------------------------------------------------------------------


class RoleResponse(BaseModel):
    """Read-only view of a Role row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    name: str
    slug: str
    primary_domain: RoleDomain
    parent_role_id: UUID | None
    is_system_role: bool
    description: str | None
    created_at: datetime
    updated_at: datetime | None


class PermissionResponse(BaseModel):
    """Read-only view of a Permission row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    resource_slug: str
    action: str
    slug: str
    description: str | None
    is_system_permission: bool
    created_at: datetime


class PersonRoleResponse(BaseModel):
    """Read-only view of a PersonRole assignment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    person_id: UUID
    role_id: UUID
    entity_instance_id: UUID | None
    assigned_at: datetime
    assigned_by_person_id: UUID | None
    revoked_at: datetime | None


class RolePermissionResponse(BaseModel):
    """Read-only view of a RolePermission grant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    role_id: UUID
    permission_id: UUID
    conditions: dict[str, Any] | None
    granted_at: datetime
    granted_by_person_id: UUID | None
    revoked_at: datetime | None
