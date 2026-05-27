"""auth middleware schema: permissions_version + auth_provider_org_id

Revision ID: f1a2b3c4d5e6
Revises: d1e2f3a4b5c6
Create Date: 2026-05-27 12:35:57.000000

Two columns required by TASK-014 (auth middleware):

* ``people.permissions_version`` — monotonic integer per ADR-012; bumped
  inside the same transaction as any PersonRole/RolePermission mutation so
  the permission cache key is immediately invalidated.

* ``organizations.auth_provider_org_id`` — the Auth0 Organization ID
  (e.g. "org_abc123") that appears in the ``org_id`` JWT claim. Populated
  by TASK-014B/E; NULL until the org is linked to Auth0.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADR-012: permission cache version column
    op.add_column(
        "people",
        sa.Column(
            "permissions_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # TASK-014 / ADR-010: Auth0 Organization binding
    op.add_column(
        "organizations",
        sa.Column("auth_provider_org_id", sa.String(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_organizations_auth_provider_org_id",
        "organizations",
        ["auth_provider_org_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_organizations_auth_provider_org_id", "organizations", type_="unique"
    )
    op.drop_column("organizations", "auth_provider_org_id")
    op.drop_column("people", "permissions_version")
