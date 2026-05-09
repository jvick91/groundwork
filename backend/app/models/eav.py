"""ORM models for the EAV domain (SPEC-001).

Organization is the root tenant record. EntityType / EntityAttribute /
EntityInstance / AttributeValue are the four-table EAV core that lets each
practice declare its own entity shapes (intake forms, assessments, custom
metadata) without schema migrations.

Per ADR-002 every FK is a scalar UUID column — no ``relationship()``.
Per ADR-009 invariants live on the model: validators, check constraints,
partial indexes, mutator methods, and ``@classmethod`` factories.
"""

import uuid
import zoneinfo
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.enums.eav import FieldType


class Organization(Base, IdMixin, TimestampMixin):
    """Root tenant record. Every other domain table scopes to this.

    Invariants (ADR-009 — Model-as-entity):

    - ``country`` and ``state`` are stored as uppercase ISO 3166 alpha-2 codes.
    - ``timezone`` is a valid IANA tz identifier.
    - ``is_active`` is a tenant-suspension toggle (NOT a soft-delete column).
      ``deactivate()`` flips it; ``OrganizationAlreadyInactive`` guards
      double-deactivation.
    """

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String, nullable=False)
    npi_number: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    timezone: Mapped[str] = mapped_column(String, nullable=False, server_default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    @validates("country")
    def _validate_country(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("country is required")
        upper = value.upper()
        if len(upper) != 2 or not upper.isalpha():
            raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code")
        return upper

    @validates("state")
    def _validate_state(self, _key: str, value: str | None) -> str | None:
        if value is None:
            return None
        upper = value.upper()
        if len(upper) != 2 or not upper.isalpha():
            raise ValueError("state must be a 2-letter ISO 3166-2 subdivision code")
        return upper

    @validates("timezone")
    def _validate_timezone(self, _key: str, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError) as err:
            raise ValueError(f"'{value}' is not a valid IANA timezone identifier") from err
        return value

    @classmethod
    def from_create(
        cls,
        *,
        name: str,
        npi_number: str | None,
        tax_id: str | None,
        phone: str | None,
        timezone: str,
        address_line1: str | None,
        address_line2: str | None,
        city: str | None,
        state: str | None,
        postal_code: str | None,
        country: str,
    ) -> "Organization":
        """Construct an Organization from primitive fields.

        The model has no dependency on the schema layer; the service maps
        the validated request body to keyword arguments here.
        """
        return cls(
            name=name,
            npi_number=npi_number,
            tax_id=tax_id,
            phone=phone,
            timezone=timezone,
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            is_active=True,
            created_at=datetime.now(tz=UTC),
        )

    def deactivate(self) -> None:
        """Mark the organization inactive (tenant suspension).

        Raises ``OrganizationAlreadyInactive`` if the organization is already
        inactive — double-deactivation is a state-transition violation.
        """
        from app.core.exceptions import OrganizationAlreadyInactive

        if not self.is_active:
            raise OrganizationAlreadyInactive(organization_id=self.id, actor_id=None)
        self.is_active = False


class EntityType(Base, IdMixin, TimestampMixin):
    """EAV type definition: ``provider``, ``client``, ``admin`` (system) plus
    org-defined custom types like ``nutritionist`` (SPEC-001 §4, §6).

    Invariants (ADR-009 — Model-as-entity):

    - System slugs ``provider`` / ``client`` / ``admin`` are globally reserved.
    - ``is_system_type`` rows cannot be renamed or deleted
      (``assert_mutable()`` raises ``ResourceLockedError`` for both).
    - Slug uniqueness within an organization is enforced by the DB
      ``UniqueConstraint`` below; the service layer pre-checks for a
      friendlier 409 envelope.
    """

    __tablename__ = "entity_types"
    __table_args__ = (
        # NULL organization_id = system type; system slugs are globally reserved
        # (application layer enforces; DB constraint covers org-scoped uniqueness)
        UniqueConstraint("organization_id", "slug"),
    )

    # System-reserved slugs — set as a frozenset class attribute so the rule
    # ships with the entity, not as module-level data (ADR-009).
    SYSTEM_SLUGS: frozenset[str] = frozenset({"provider", "client", "admin"})

    # NULLABLE: NULL means system-scoped type (provider, client, admin)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    is_system_type: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_person_subtype: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    def assert_mutable(self, *, action: str) -> None:
        """Guard system types from rename/delete (SPEC-001 §4).

        Raises ``ResourceLockedError`` with the specific reason for
        ``action``. ``action`` should be ``"rename"`` or ``"delete"`` for
        message clarity.
        """
        from app.core.exceptions import ResourceLockedError

        if self.is_system_type:
            reason = (
                "system types cannot be renamed or modified"
                if action == "rename"
                else "system types cannot be deleted"
            )
            raise ResourceLockedError("EntityType", reason)


class EntityAttribute(Base, IdMixin, TimestampMixin):
    __tablename__ = "entity_attributes"

    entity_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_types.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    field_type: Mapped[FieldType] = mapped_column(
        SAEnum(FieldType, native_enum=False), nullable=False
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Can be a list (enum options) or a string (FK target slug) — stored as JSONB
    options: Mapped[Any] = mapped_column(JSONB, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class EntityInstance(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "entity_instances"

    entity_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_types.id"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # Set when EntityType.is_person_subtype = true; bridges to identity layer
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class AttributeValue(Base, IdMixin):
    """
    IdMixin only — no timestamps by design (SPEC-001 §2).
    Value changes are tracked via AuditLog on the parent EntityInstance.
    """

    __tablename__ = "attribute_values"
    __table_args__ = (UniqueConstraint("entity_instance_id", "entity_attribute_id"),)

    entity_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    entity_attribute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_attributes.id"), nullable=False
    )
    # Always stored as text; cast by field_type at application layer (SPEC-001 §2)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
