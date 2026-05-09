"""ORM models for the Billing & Payments domain (SPEC-005)."""

import uuid
from datetime import date, datetime

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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.enums.billing import (
    InsurancePriority,
    InvoiceStatus,
    PayerType,
    PaymentMethod,
    PaymentStatus,
)


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
