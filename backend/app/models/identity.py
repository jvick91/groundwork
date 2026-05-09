"""ORM models for the Identity / RBAC domain (SPEC-002).

Person is tenant-independent. Tenant scoping enters via PersonRole.
PersonRole and RolePermission carry ``revoked_at`` as a domain column —
revoked rows remain in place for audit (ADR-003 partial unique indexes
exclude them).
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.enums.identity import RoleDomain


class Person(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """
    Tenant-independent. One Person row per human regardless of org count.
    Tenant scoping is enforced at PersonRole.organization_id.
    """

    __tablename__ = "people"

    # Stable Auth0 subject. NULL for non-authenticating personas (clients, guardians MVP)
    auth_subject: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    # PHI — excluded from AuditLog snapshots per BR-08
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Role(Base, IdMixin, TimestampMixin):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    # NULL = system role (globally reserved slug)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    primary_domain: Mapped[RoleDomain] = mapped_column(
        SAEnum(RoleDomain, native_enum=False), nullable=False
    )
    # Self-referencing FK for role hierarchy
    parent_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True
    )
    is_system_role: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Permission(Base, IdMixin, TimestampMixin):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    # NULL = system permission (globally reserved slug)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    resource_slug: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    # Canonical slug: resource_slug.action (e.g., clients.read)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_permission: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class PersonRole(Base, IdMixin, TimestampMixin):
    """
    Three-way binding: Person + Role + EntityInstance per Organization.
    revoked_at is a domain column — not soft delete (revoked rows are historical).
    """

    __tablename__ = "person_roles"
    __table_args__ = (
        # A person cannot hold duplicate active copies of the same scoped role
        Index(
            "uq_person_roles_active",
            "organization_id",
            "person_id",
            "role_id",
            "entity_instance_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    # Required when role.primary_domain maps to a person_subtype EntityType
    entity_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    assigned_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    # NULL = active; non-null = revoked (historical, does not block re-assignment)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RolePermission(Base, IdMixin, TimestampMixin):
    """
    Grants a permission to a role with optional row-level filtering conditions.
    revoked_at is a domain column — not soft delete.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (
        Index(
            "uq_role_permissions_active",
            "organization_id",
            "role_id",
            "permission_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False
    )
    # Row-level filtering rules — see SPEC-002 §6
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    granted_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
