"""
Pydantic schemas for the Identity domain (SPEC-002 §2).

Person is tenant-independent. Schemas are the HTTP contract; the service
layer maps fields onto the ORM and never returns these `*Response` types
itself (ADR-009 amendment — services don't construct Response schemas).
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.enums.identity import InvitationState, InvitationType, RoleDomain


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


# ---------------------------------------------------------------------------
# Invitation schemas (TASK-014F / ADR-011)
# ---------------------------------------------------------------------------


class _InvitationCreateBase(BaseModel):
    """Fields common to all invitation types."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr = Field(..., description="Invitee's email address.")
    planned_role_slug: str = Field(
        ..., min_length=1, max_length=128, description="Role slug to grant on accept."
    )


class ProviderInvitationCreate(_InvitationCreateBase):
    """Type 1 — invite a new provider.  Requires entity instance info."""

    type: Literal[InvitationType.PROVIDER]
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    planned_entity_instance_id: UUID | None = Field(
        default=None,
        description="Existing EntityInstance to bind the provider role to.",
    )
    planned_entity_instance_payload: dict[str, Any] | None = Field(
        default=None,
        description="If set, an EntityInstance is created from this payload on accept.",
    )

    @model_validator(mode="after")
    def _require_entity_instance(self) -> "ProviderInvitationCreate":
        if (
            self.planned_entity_instance_id is None
            and self.planned_entity_instance_payload is None
        ):
            raise ValueError(
                "Provider invitations require either planned_entity_instance_id "
                "or planned_entity_instance_payload."
            )
        return self


class AdminInvitationCreate(_InvitationCreateBase):
    """Type 2 — invite a new admin."""

    type: Literal[InvitationType.ADMIN]
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)


class SystemAdminInvitationCreate(_InvitationCreateBase):
    """Type 3 — invite a new system_admin.  Caller must be a system_admin."""

    type: Literal[InvitationType.SYSTEM_ADMIN]
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)


class CrossOrgInvitationCreate(_InvitationCreateBase):
    """Type 4 — add an existing Person from another org.

    first_name / last_name are omitted: the Person record already exists.
    """

    type: Literal[InvitationType.CROSS_ORG]


# Discriminated union — FastAPI reads the ``type`` field to pick the right validator.
InvitationCreate = Annotated[
    ProviderInvitationCreate
    | AdminInvitationCreate
    | SystemAdminInvitationCreate
    | CrossOrgInvitationCreate,
    Field(discriminator="type"),
]


class InvitationSendResponse(BaseModel):
    """Uniform response shape for POST /invitations (ADR-011 §uniform-response).

    Identical regardless of invite type or whether the email maps to an
    existing Person — prevents cross-tenant enumeration.
    """

    status: Literal["pending"] = "pending"
    invitation_id: UUID


class InvitationResponse(BaseModel):
    """Full invitation detail returned by GET /invitations/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    type: InvitationType
    email: str
    first_name: str | None
    last_name: str | None
    planned_role_slug: str
    planned_entity_instance_id: UUID | None
    planned_entity_instance_payload: dict[str, Any] | None
    state: InvitationState
    auth0_invitation_id: str | None
    created_by_person_id: UUID
    expires_at: datetime
    accepted_at: datetime | None
    expired_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class InvitationAcceptRequest(BaseModel):
    """Body for POST /invitations/accept.

    The JWT is validated against Auth0 JWKS inside the service; ``sub`` and
    ``org_id`` claims are read from it.  No ``X-Organization-Id`` header is
    required — the invitation row carries the org.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    nonce: str = Field(
        ..., min_length=1, max_length=512, description="Single-use invitation nonce."
    )
    jwt: str = Field(..., min_length=1, description="Auth0 JWT issued to the invitee.")


class InvitationAcceptResponse(BaseModel):
    """Response from POST /invitations/accept."""

    person_id: UUID
    person_role_id: UUID


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
