"""
SQLAlchemy ORM models — all 26 tables across 6 domains.

Generated from:
  SPEC-001 (EAV), SPEC-002 (Identity), SPEC-003 (Scheduling),
  SPEC-004 (Clinical), SPEC-005 (Billing), SPEC-006 (Compliance)

Conventions:
  - SQLAlchemy 2 Mapped / mapped_column throughout
  - native_enum=False on all SAEnum columns (stored as VARCHAR, easier migrations)
  - No relationship() — foreign key columns only
  - AuditLog uses IdMixin only: spec explicitly forbids updated_at/deleted_at
  - FormTemplate.schema stored as "schema" column, Python attr is schema_
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, SoftDeleteMixin, TimestampMixin

# ---------------------------------------------------------------------------
# Enums — one StrEnum per domain, defined before the model that uses it
# ---------------------------------------------------------------------------


# EAV
class FieldType(StrEnum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    BOOL = "BOOL"
    ENUM = "ENUM"
    FK = "FK"
    JSONB = "JSONB"


# Identity
class RoleDomain(StrEnum):
    ADMIN = "ADMIN"
    PROVIDER = "PROVIDER"
    CLIENT = "CLIENT"


# Scheduling
class SessionStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


# Clinical
class NoteFormat(StrEnum):
    SOAP = "SOAP"
    DAP = "DAP"
    BIRP = "BIRP"


class NoteStatus(StrEnum):
    DRAFT = "DRAFT"
    SIGNED = "SIGNED"
    COSIGNED = "COSIGNED"
    AMENDMENT_PENDING = "AMENDMENT_PENDING"


# Billing
class InsurancePriority(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class PaymentMethod(StrEnum):
    CASH = "CASH"
    CHECK = "CHECK"
    CARD = "CARD"
    ACH = "ACH"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class PayerType(StrEnum):
    CLIENT = "CLIENT"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class PaymentStatus(StrEnum):
    POSTED = "POSTED"
    VOIDED = "VOIDED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    VOID = "VOID"


# Compliance
class ConsentStatus(StrEnum):
    PENDING = "PENDING"
    SIGNED = "SIGNED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class FormType(StrEnum):
    INTAKE = "INTAKE"
    ASSESSMENT = "ASSESSMENT"
    CONSENT = "CONSENT"
    CUSTOM = "CUSTOM"


# ---------------------------------------------------------------------------
# EAV Domain  (SPEC-001)
# ---------------------------------------------------------------------------


class Organization(Base, IdMixin, TimestampMixin):
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
    # is_active is a tenant suspension toggle, NOT a soft-delete column
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class EntityType(Base, IdMixin, TimestampMixin):
    __tablename__ = "entity_types"
    __table_args__ = (
        # NULL organization_id = system type; system slugs are globally reserved
        # (application layer enforces; DB constraint covers org-scoped uniqueness)
        UniqueConstraint("organization_id", "slug"),
    )

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


# ---------------------------------------------------------------------------
# Identity Domain  (SPEC-002)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scheduling Domain  (SPEC-003)
# ---------------------------------------------------------------------------


class AppointmentType(Base, IdMixin, TimestampMixin):
    __tablename__ = "appointment_types"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    default_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    cpt_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpt_codes.id"), nullable=True
    )
    is_telehealth: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_intake: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Session(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sessions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    appointment_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_types.id"), nullable=False
    )
    # Bridge rule: must reference an EntityInstance of type provider
    provider_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    # Bridge rule: must reference an EntityInstance of type client
    client_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, native_enum=False),
        nullable=False,
        server_default=SessionStatus.SCHEDULED,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    # Internal scheduling notes — not PHI, not a clinical note
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Clinical Domain  (SPEC-004)
# ---------------------------------------------------------------------------


class ClinicalNote(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "clinical_notes"
    __table_args__ = (
        # One note per session including soft-deleted rows
        UniqueConstraint("session_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    # Bridge rule: must reference an EntityInstance of type provider
    author_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    # Set at creation, immutable thereafter
    note_format: Mapped[NoteFormat] = mapped_column(
        SAEnum(NoteFormat, native_enum=False), nullable=False
    )
    status: Mapped[NoteStatus] = mapped_column(
        SAEnum(NoteStatus, native_enum=False),
        nullable=False,
        server_default=NoteStatus.DRAFT,
    )
    # PHI — keys depend on note_format (SOAP/DAP/BIRP); excluded from AuditLog per BR-08
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Set once at first signing; immutable thereafter
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    cosigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cosigned_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    cosign_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Append-only addendum; never replaces signed content
    amendment_note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Billing Domain  (SPEC-005)
# ---------------------------------------------------------------------------


class CPTCode(Base, IdMixin, TimestampMixin):
    __tablename__ = "cpt_codes"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    default_rate_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ICDCode(Base, IdMixin, TimestampMixin):
    __tablename__ = "icd_codes"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class InsurancePayer(Base, IdMixin, TimestampMixin):
    __tablename__ = "insurance_payers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    payer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ClientInsurance(Base, IdMixin, TimestampMixin):
    __tablename__ = "client_insurances"
    __table_args__ = (
        # A client cannot have two active records of the same priority with the same payer
        Index(
            "uq_client_insurances_active_priority",
            "organization_id",
            "client_instance_id",
            "insurance_payer_id",
            "priority",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # Bridge rule: must reference an EntityInstance of type client
    client_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    insurance_payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insurance_payers.id"), nullable=False
    )
    member_id: Mapped[str] = mapped_column(String, nullable=False)
    group_number: Mapped[str | None] = mapped_column(String, nullable=True)
    plan_name: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[InsurancePriority] = mapped_column(
        SAEnum(InsurancePriority, native_enum=False), nullable=False
    )
    copay_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deductible_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deductible_met_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Invoice(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        # One non-voided invoice per session; voided rows don't block replacement
        Index(
            "uq_invoices_active_per_session",
            "session_id",
            unique=True,
            postgresql_where=text("status != 'void'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    # Derived from session at creation — not accepted as independent input
    client_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    provider_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, native_enum=False),
        nullable=False,
        server_default=InvoiceStatus.DRAFT,
    )
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Computed and stored atomically at write time — never computed on the fly
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    amount_paid_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class InvoiceLineItem(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "invoice_line_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False
    )
    cpt_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpt_codes.id"), nullable=False
    )
    # PHI when correlated to a client — excluded from AuditLog per BR-08
    icd_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("icd_codes.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_rate_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # Computed as unit_rate_cents * units; stored for invoice total recomputation
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)


class Payment(Base, IdMixin, TimestampMixin):
    __tablename__ = "payments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, native_enum=False), nullable=False
    )
    payer_type: Mapped[PayerType] = mapped_column(
        SAEnum(PayerType, native_enum=False), nullable=False
    )
    # Required when payer_type = insurance (enforced at application layer)
    insurance_payer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insurance_payers.id"), nullable=True
    )
    reference_number: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, native_enum=False),
        nullable=False,
        server_default=PaymentStatus.POSTED,
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Compliance Domain  (SPEC-006)
# ---------------------------------------------------------------------------


class AuditLog(Base, IdMixin):
    """
    IdMixin only — SPEC-006 §2 explicitly forbids updated_at and deleted_at.
    AuditLog is append-only and immutable. occurred_at replaces created_at.
    No SoftDeleteMixin, no TimestampMixin.
    """

    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # NULL for system/cron-initiated events (e.g., expire_consents)
    actor_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    # Not a FK — can reference any table's PK
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # PHI-filtered snapshots — see BR-08 and audit-logging.mdc
    previous_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    next_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class DocumentType(Base, IdMixin, TimestampMixin):
    __tablename__ = "document_types"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    # Valid values: session, clinical_note, invoice, entity_instance, person
    linked_resource_table: Mapped[str | None] = mapped_column(String, nullable=True)
    is_system_type: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Document(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """S3 object is NOT removed on soft delete (see SPEC-006 §4, ADR-005)."""

    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    document_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_types.id"), nullable=False
    )
    uploaded_by_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False
    )
    linked_resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Never exposed in API responses — used only for presigned URL generation
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String, nullable=False)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ConsentType(Base, IdMixin, TimestampMixin):
    __tablename__ = "consent_types"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    is_system_type: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class ClientConsent(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "client_consents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # Bridge rule: must reference an EntityInstance of type client
    client_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entity_instances.id"), nullable=False
    )
    consent_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consent_types.id"), nullable=False
    )
    status: Mapped[ConsentStatus] = mapped_column(
        SAEnum(ConsentStatus, native_enum=False), nullable=False
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    form_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_templates.id"), nullable=True
    )
    # PHI — excluded from AuditLog snapshots per BR-08
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FormTemplate(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "form_templates"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    form_type: Mapped[FormType] = mapped_column(SAEnum(FormType, native_enum=False), nullable=False)
    # Python attr is schema_ to avoid collision with SQLAlchemy's .schema property
    schema_: Mapped[dict[str, Any]] = mapped_column(JSONB, name="schema", nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False, server_default="1.0.0")
    is_system_template: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
