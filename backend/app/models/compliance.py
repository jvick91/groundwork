"""ORM models for the Compliance domain (SPEC-006).

AuditLog is append-only and uses IdMixin only — SPEC-006 §2 forbids
``updated_at`` and ``deleted_at``. ``occurred_at`` replaces ``created_at``.
The ``outcome`` column distinguishes success from failure audits
(ADR-009: failure audits are written by the route-level exception handler
in a fresh session).
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.enums.compliance import ConsentStatus, FormType


class AuditLog(Base, IdMixin):
    """
    IdMixin only — SPEC-006 §2 explicitly forbids updated_at and deleted_at.
    AuditLog is append-only and immutable. occurred_at replaces created_at.
    No SoftDeleteMixin, no TimestampMixin.

    The ``outcome`` column (ADR-009) distinguishes success-path audits
    (written in the request transaction by AuditWriter) from failure-path
    audits (written by the route-level exception handler in a fresh
    session). Always one of: ``"success"`` or ``"failure"``.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'failure')",
            name="ck_audit_logs_outcome",
        ),
    )

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
    # 'success' on the request-transaction path; 'failure' from the route-level
    # exception handler in a fresh session (ADR-009).
    outcome: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'success'"),
    )
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
