"""add audit_log_outcome column (ADR-009)

Adds an ``outcome`` column to ``audit_logs`` with values ``'success'`` or
``'failure'``. Success-path audits — written by ``AuditWriter`` from the
request session — carry ``'success'``. Failure-path audits — written by
the route-level exception handler in a fresh session — carry ``'failure'``.

Revision ID: e730417d99c0
Revises: 485f37aa7554
Create Date: 2026-05-09
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e730417d99c0"
down_revision: Union[str, None] = "485f37aa7554"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column(
            "outcome",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'success'"),
        ),
    )
    # Naming convention prepends ``ck_audit_logs_`` to the constraint name.
    op.create_check_constraint(
        "outcome_valid",
        "audit_logs",
        "outcome IN ('success', 'failure')",
    )


def downgrade() -> None:
    op.drop_constraint("outcome_valid", "audit_logs", type_="check")
    op.drop_column("audit_logs", "outcome")
