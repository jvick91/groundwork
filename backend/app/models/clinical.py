"""ORM models for the Clinical Notes domain (SPEC-004)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
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
from app.enums.clinical import NoteFormat, NoteStatus


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
