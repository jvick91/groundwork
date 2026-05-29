"""invitation table

Revision ID: b3c4d5e6f7a8
Revises: f1a2b3c4d5e6
Create Date: 2026-05-28 21:00:00.000000

Introduces the ``invitations`` table per ADR-011 (TASK-014F).

The table is the send-side of the invitation flow. No PersonRole rows exist
until the accept transaction (TASK-014G). The partial unique index
``uq_invitations_pending_email`` follows ADR-003: one pending invite per
email per org; historical (revoked / expired / accepted) rows are exempt.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b3c4d5e6f7a8"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "provider", "admin", "system_admin", "cross_org",
                name="invitationtype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("planned_role_slug", sa.String(), nullable=False),
        sa.Column("planned_entity_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planned_entity_instance_payload", postgresql.JSONB(), nullable=True),
        sa.Column("nonce", sa.String(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending", "accepted", "expired", "revoked",
                name="invitationstate",
                native_enum=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("auth0_invitation_id", sa.String(), nullable=True),
        sa.Column("created_by_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_person_id"], ["people.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["planned_entity_instance_id"], ["entity_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Unique nonce index (covers all states — nonces are never reused)
    op.create_index("ix_invitations_nonce", "invitations", ["nonce"], unique=True)

    # Partial unique index: one pending invite per email per org (ADR-003)
    op.create_index(
        "uq_invitations_pending_email",
        "invitations",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_invitations_pending_email", table_name="invitations")
    op.drop_index("ix_invitations_nonce", table_name="invitations")
    op.drop_table("invitations")
    op.execute("DROP TYPE IF EXISTS invitationtype")
    op.execute("DROP TYPE IF EXISTS invitationstate")
