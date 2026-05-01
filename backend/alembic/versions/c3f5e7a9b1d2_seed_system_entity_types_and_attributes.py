"""Seed system EntityTypes and EntityAttributes (SPEC-001 §3).

Creates the three system EntityTypes (provider, client, admin) and their
seed EntityAttributes. Rows have is_system_type = true and cannot be deleted
or renamed via the API.

Revision ID: c3f5e7a9b1d2
Revises: b2e4f6a8c0d1
Create Date: 2026-04-30

"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3f5e7a9b1d2"
down_revision = "b2e4f6a8c0d1"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Fixed UUIDs so the migration is idempotent and referenceble downstream.
# ---------------------------------------------------------------------------
PROVIDER_ID = "00000000-0000-0000-0000-000000000001"
CLIENT_ID = "00000000-0000-0000-0000-000000000002"
ADMIN_ID = "00000000-0000-0000-0000-000000000003"


def upgrade() -> None:
    now = sa.func.now()

    # ------------------------------------------------------------------
    # Insert system EntityTypes
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO entity_types
                (id, organization_id, name, slug, is_system_type, is_person_subtype, created_at, updated_at)
            VALUES
                (:provider_id, NULL, 'provider', 'provider', true, true, now(), now()),
                (:client_id,   NULL, 'client',   'client',   true, true, now(), now()),
                (:admin_id,    NULL, 'admin',     'admin',    true, true, now(), now())
            ON CONFLICT DO NOTHING
            """
        ).bindparams(
            provider_id=PROVIDER_ID,
            client_id=CLIENT_ID,
            admin_id=ADMIN_ID,
        )
    )

    # ------------------------------------------------------------------
    # Provider attributes (SPEC-001 §3)
    # ------------------------------------------------------------------
    provider_attrs = [
        ("license_number", "License Number", "TEXT", True, None, 0),
        ("license_state", "License State", "TEXT", True, None, 1),
        ("npi_number", "NPI Number", "TEXT", False, None, 2),
        ("specialty", "Specialty", "TEXT", False, None, 3),
        ("taxonomy_code", "Taxonomy Code", "TEXT", False, None, 4),
        ("dea_number", "DEA Number", "TEXT", False, None, 5),
    ]
    for name, display_name, field_type, is_required, options, display_order in provider_attrs:
        op.execute(
            sa.text(
                """
                INSERT INTO entity_attributes
                    (id, entity_type_id, name, display_name, field_type,
                     is_required, options, display_order, created_at, updated_at)
                VALUES
                    (:id, :type_id, :name, :display_name, :field_type,
                     :is_required, :options::jsonb, :display_order, now(), now())
                ON CONFLICT DO NOTHING
                """
            ).bindparams(
                id=str(uuid4()),
                type_id=PROVIDER_ID,
                name=name,
                display_name=display_name,
                field_type=field_type,
                is_required=is_required,
                options=options,
                display_order=display_order,
            )
        )

    # ------------------------------------------------------------------
    # Client attributes (SPEC-001 §3)
    # intake_status is an ENUM with options ["new","in_progress","complete"]
    # ------------------------------------------------------------------
    client_attrs = [
        ("intake_status", "Intake Status", "ENUM", True, '["new","in_progress","complete"]', 0),
        ("referral_source", "Referral Source", "TEXT", False, None, 1),
        ("emergency_contact_name", "Emergency Contact Name", "TEXT", False, None, 2),
        ("emergency_contact_phone", "Emergency Contact Phone", "TEXT", False, None, 3),
        ("onboarded_at", "Onboarded At", "DATE", False, None, 4),
    ]
    for name, display_name, field_type, is_required, options, display_order in client_attrs:
        op.execute(
            sa.text(
                """
                INSERT INTO entity_attributes
                    (id, entity_type_id, name, display_name, field_type,
                     is_required, options, display_order, created_at, updated_at)
                VALUES
                    (:id, :type_id, :name, :display_name, :field_type,
                     :is_required, :options::jsonb, :display_order, now(), now())
                ON CONFLICT DO NOTHING
                """
            ).bindparams(
                id=str(uuid4()),
                type_id=CLIENT_ID,
                name=name,
                display_name=display_name,
                field_type=field_type,
                is_required=is_required,
                options=options,
                display_order=display_order,
            )
        )

    # ------------------------------------------------------------------
    # Admin attributes (SPEC-001 §3)
    # ------------------------------------------------------------------
    admin_attrs = [
        ("department", "Department", "TEXT", False, None, 0),
        ("title", "Title", "TEXT", False, None, 1),
    ]
    for name, display_name, field_type, is_required, options, display_order in admin_attrs:
        op.execute(
            sa.text(
                """
                INSERT INTO entity_attributes
                    (id, entity_type_id, name, display_name, field_type,
                     is_required, options, display_order, created_at, updated_at)
                VALUES
                    (:id, :type_id, :name, :display_name, :field_type,
                     :is_required, :options::jsonb, :display_order, now(), now())
                ON CONFLICT DO NOTHING
                """
            ).bindparams(
                id=str(uuid4()),
                type_id=ADMIN_ID,
                name=name,
                display_name=display_name,
                field_type=field_type,
                is_required=is_required,
                options=options,
                display_order=display_order,
            )
        )


def downgrade() -> None:
    # Remove seed attributes first (FK), then entity types.
    op.execute(
        sa.text(
            "DELETE FROM entity_attributes WHERE entity_type_id IN (:p, :c, :a)"
        ).bindparams(p=PROVIDER_ID, c=CLIENT_ID, a=ADMIN_ID)
    )
    op.execute(
        sa.text(
            "DELETE FROM entity_types WHERE id IN (:p, :c, :a)"
        ).bindparams(p=PROVIDER_ID, c=CLIENT_ID, a=ADMIN_ID)
    )
